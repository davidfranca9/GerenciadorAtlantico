from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    # Pode vir vazio (nenhuma aba) ou nulo (usuario ainda nao migrado da lista
    # negra antiga); o menu trata os dois como "nenhuma aba liberada".
    paginas_liberadas: str | None = ""

    class Config:
        from_attributes = True


# --------------------------------------------------------------------------
# Telas do sistema e permissao por usuario
# --------------------------------------------------------------------------
# Esta e a lista unica das abas do sistema, nos mesmos grupos e na mesma ordem
# da barra lateral. O menu (frontend/src/components/Layout.jsx) so desenha
# icone e descricao; o que existe e quem pode ver sai daqui, e tem teste
# conferindo que as duas listas batem (tests/test_permissao_telas.py) - assim
# aba nova nao nasce de fora da permissao sem ninguem perceber.
#
# Antes a permissao era lista negra ("paginas_bloqueadas"): aba nova nascia
# liberada pra todo mundo e so sumia depois que alguem lembrasse de bloquear.
# Agora e lista de permissao ("paginas_liberadas"): aba nova nasce fechada e o
# administrador marca, usuario por usuario, quem ve o que.


def _tela(rota: str, nome: str, *, somente_admin: bool = False, sempre_liberada: bool = False) -> dict:
    """somente_admin: o backend da area exige administrador, nao da pra liberar.
    sempre_liberada: todo usuario logado ve (a propria senha, por exemplo)."""
    return {"rota": rota, "nome": nome, "somente_admin": somente_admin, "sempre_liberada": sempre_liberada}


GRUPOS_TELAS: tuple[dict, ...] = (
    {"titulo": "Operação", "telas": (
        _tela("/dashboard", "Dashboard"),
        _tela("/pedidos", "Pedidos"),
        _tela("/contrato", "Contratos"),
        _tela("/ordem-coleta", "Ordem de coleta"),
        _tela("/autorizacao-abastecimento", "Autorização de abastecimento"),
        _tela("/agendamentos", "Agendamentos"),
        _tela("/analise-fretes", "Análise de fretes"),
        _tela("/documentos-fiscais", "Documentos fiscais"),
    )},
    {"titulo": "Financeiro", "telas": (
        _tela("/financeiro/caixa", "Caixa"),
        _tela("/financeiro/carregamentos", "Carregamentos"),
        _tela("/financeiro/lucro-bruto", "Lucro bruto"),
        _tela("/financeiro/gastos", "Gastos"),
        _tela("/financeiro/precificacao", "Precificação CT-e"),
        _tela("/financeiro/pagamentos", "Pagamentos"),
        _tela("/financeiro/faturas", "Faturas de abastecimento"),
        _tela("/financeiro/agenciamentos", "Agenciamentos"),
        _tela("/financeiro/dividas", "Dívidas ativas"),
    )},
    {"titulo": "Comunicação", "telas": (
        _tela("/emails", "E-mails"),
        _tela("/whatsapp", "WhatsApp"),
    )},
    {"titulo": "Integrações", "telas": (
        _tela("/bsoft", "Bsoft TMS"),
    )},
    {"titulo": "Cadastros", "telas": (
        _tela("/clientes", "Clientes"),
    )},
    {"titulo": "Sistema", "telas": (
        # Administracao e Configuracoes mexem no sistema inteiro (usuarios,
        # senhas, listas de e-mail): o backend delas exige administrador, entao
        # nao entram na marcacao por usuario.
        _tela("/admin", "Administração", somente_admin=True),
        _tela("/configuracoes", "Configurações", somente_admin=True),
        _tela("/trocar-senha", "Segurança", sempre_liberada=True),
    )},
)

TODAS_AS_TELAS: tuple[dict, ...] = tuple(tela for grupo in GRUPOS_TELAS for tela in grupo["telas"])
ROTAS_TELAS: frozenset[str] = frozenset(tela["rota"] for tela in TODAS_AS_TELAS)
# O que o administrador marca por usuario na tela de Administracao.
TELAS_LIBERAVEIS: tuple[str, ...] = tuple(
    tela["rota"] for tela in TODAS_AS_TELAS if not tela["somente_admin"] and not tela["sempre_liberada"]
)
TELAS_SEMPRE_LIBERADAS: frozenset[str] = frozenset(tela["rota"] for tela in TODAS_AS_TELAS if tela["sempre_liberada"])
# Migracao da lista negra antiga: o financeiro era so-admin e nunca aparecia na
# lista de bloqueio, entao quem nao e administrador nunca via essas abas - elas
# ficam de fora de quem vinha da lista negra pra ninguem ganhar acesso novo.
TELAS_DA_LISTA_NEGRA_ANTIGA: tuple[str, ...] = tuple(
    rota for rota in TELAS_LIBERAVEIS if not rota.startswith("/financeiro/")
)


def telas_do_texto(texto: str | None) -> list[str]:
    """Le a coluna (rotas separadas por virgula) na ordem do menu, sem repetir.

    Rota desconhecida cai fora: tela que deixou de existir (ou com o nome
    errado) nao vira permissao solta."""
    marcadas = {pedaco.strip() for pedaco in (texto or "").split(",") if pedaco.strip()}
    return [rota for rota in TELAS_LIBERAVEIS if rota in marcadas]


def telas_liberadas(user) -> set[str]:
    """Telas que esse usuario pode abrir. Administrador ve todas, sempre."""
    if getattr(user, "role", "") == "admin":
        return set(ROTAS_TELAS)
    return set(telas_do_texto(getattr(user, "paginas_liberadas", ""))) | set(TELAS_SEMPRE_LIBERADAS)


def tem_tela(user, *rotas: str) -> bool:
    """Basta uma das telas: tem rota que serve mais de uma aba (as contas
    bancarias, por exemplo, alimentam Pagamentos, Faturas e Dívidas)."""
    return bool(telas_liberadas(user).intersection(rotas))


def migrar_para_lista_de_permissao(db) -> int:
    """Lista negra -> lista de permissao, uma vez por usuario (roda no startup).

    Quem ja usava o sistema continua com exatamente as mesmas abas: tudo o que
    estava liberado antes, ou seja, as telas da lista negra menos as que
    estavam bloqueadas pra ele. O financeiro era so de administrador e nunca
    entrava na lista negra, entao ninguem ganha financeiro de brinde - o dono
    marca isso na mao, na tela de Administracao.

    So mexe em quem esta com a coluna NULL ("nunca migrado"): subir o servidor
    de novo nao desfaz o que o dono configurou depois.
    """
    pendentes = db.query(User).filter(User.paginas_liberadas.is_(None)).all()
    for user in pendentes:
        bloqueadas = {pedaco.strip() for pedaco in (user.paginas_bloqueadas or "").split(",") if pedaco.strip()}
        user.paginas_liberadas = ",".join(rota for rota in TELAS_DA_LISTA_NEGRA_ANTIGA if rota not in bloqueadas)
    if pendentes:
        db.commit()
    return len(pendentes)


def exigir_tela(*rotas: str):
    """Dependencia pra rota de leitura: passa quem tem pelo menos uma das telas
    liberadas (e o administrador, que tem todas). Gravacao segue com
    require_admin - esconder a aba no menu nao protege nada."""

    def checar(user: User = Depends(get_current_user)) -> User:
        if not tem_tela(user, *rotas):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem acesso a essa tela",
            )
        return user

    return checar


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais invalidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        email = payload.get("sub")
        if email is None:
            raise credentials_error
    except JWTError:
        raise credentials_error

    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        raise credentials_error
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a administradores")
    return user


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha incorretos")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desativado")
    return TokenResponse(access_token=create_access_token(user.email))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Senha atual incorreta")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A nova senha deve ter ao menos 8 caracteres")
    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}
