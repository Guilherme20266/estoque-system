from flask import (
    Flask, jsonify, render_template, request, redirect,
    session, flash, Response, send_file, url_for
)

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from openpyxl import Workbook
from io import BytesIO
import os, json


app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", "teste123")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=20)

db_url = os.getenv("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================
# PERMISSÕES PADRÃO (IGUAL HTML)
# ==========================
PERMISSOES_PADRAO = [
    "cadastrar_produto",
    "consultar",
    "inventario",
    "movimentacao",
    "transferencia",
    "editar_produto",
    "excluir_produto",
    "historico",
    "admin"
]


# ==========================
# MODELOS
# ==========================
class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50))
    nome = db.Column(db.String(200))
    quantidade = db.Column(db.Integer, default=0)
    validade = db.Column(db.String(20))
    endereco = db.Column(db.String(50), unique=True, nullable=False)


class Historico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(30))
    usuario = db.Column(db.String(100))
    acao = db.Column(db.String(50))
    produto = db.Column(db.String(200))
    quantidade = db.Column(db.Integer)
    origem = db.Column(db.String(255))
    destino = db.Column(db.String(255))


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(100), unique=True)
    senha = db.Column(db.String(100))
    perfil = db.Column(db.String(20))
    permissoes = db.Column(db.Text, default="[]")


# ==========================
# HELPERS
# ==========================
def logado():
    return session.get("usuario")


def tem_permissao(permissao):
    usuario = session.get("usuario")
    if not usuario:
        return False

    user = Usuario.query.filter_by(usuario=usuario).first()
    if not user:
        return False

    try:
        permissoes = json.loads(user.permissoes or "[]")
    except:
        permissoes = []

    # ADMIN só tem acesso se estiver na lista também
    return permissao in permissoes


# ==========================
# LOGIN
# ==========================
@app.route("/")
def login():
    if logado():
        return redirect("/menu")
    return render_template("login.html")


@app.route("/entrar", methods=["POST"])
def entrar():
    user = Usuario.query.filter_by(
        usuario=request.form["usuario"],
        senha=request.form["senha"]
    ).first()

    if not user:
        return redirect("/")

    session["usuario"] = user.usuario
    session["perfil"] = user.perfil
    session.permanent = True

    return redirect("/menu")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/menu")
def menu():
    if not logado():
        return redirect("/")
    return render_template("menu.html")


# ==========================
# CADASTRO
# ==========================
@app.route("/cadastrar", methods=["GET", "POST"])
def cadastrar():
    if not tem_permissao("cadastrar_produto"):
        return redirect("/menu")

    if request.method == "POST":

        endereco = f"{request.form['rua']}-{request.form['coluna']}-{request.form['nivel']}"

        if Produto.query.filter_by(endereco=endereco).first():
            return redirect("/cadastrar?erro=endereco")

        produto = Produto(
            codigo=request.form["codigo"],
            nome=request.form["nome"],
            quantidade=int(request.form["quantidade"]),
            validade=request.form["validade"],
            endereco=endereco
        )

        db.session.add(produto)
        db.session.commit()

        return redirect("/cadastrar?ok=1")

    return render_template("cadastrar.html")


# ==========================
# INVENTÁRIO
# ==========================
@app.route("/inventario")
def inventario():
    if not tem_permissao("inventario"):
        return redirect("/menu")

    produtos = Produto.query.all()
    return render_template("inventario.html", produtos=produtos)


# ==========================
# MOVIMENTAÇÃO
# ==========================
@app.route("/movimentacao", methods=["GET", "POST"])
def movimentacao():
    if not tem_permissao("movimentacao"):
        return redirect("/menu")

    produtos = Produto.query.all()

    if request.method == "POST":
        produto = Produto.query.get(request.form["produto_id"])
        qtd = int(request.form["quantidade"])
        acao = request.form["acao"]

        if acao == "entrada":
            produto.quantidade += qtd
        elif acao == "saida":
            produto.quantidade -= qtd

        db.session.commit()

    return render_template("movimentacao.html", produtos=produtos)


# ==========================
# TRANSFERÊNCIA
# ==========================
@app.route("/transferencia", methods=["GET", "POST"])
def transferencia():
    if not tem_permissao("transferencia"):
        return redirect("/menu")

    if request.method == "POST":
        produto = Produto.query.get(request.form["produto_id"])
        produto.endereco = request.form["novo_endereco"]
        db.session.commit()

    return render_template("transferencia.html")


# ==========================
# HISTÓRICO
# ==========================
@app.route("/historico")
def historico():
    if not tem_permissao("historico"):
        return redirect("/menu")

    registros = Historico.query.order_by(Historico.id.desc()).all()
    return render_template("historico.html", registros=registros)


# ==========================
# EXCLUIR
# ==========================
@app.route("/excluir/<int:id>")
def excluir(id):
    if not tem_permissao("excluir_produto"):
        return redirect("/inventario")

    p = Produto.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()

    return redirect("/inventario")


# ==========================
# ADMIN
# ==========================
@app.route("/administracao")
def administracao():
    if not tem_permissao("admin"):
        return redirect("/menu")

    usuarios = Usuario.query.all()
    return render_template("administracao.html", usuarios=usuarios)


# ==========================
# PERMISSÕES
# ==========================
@app.route("/usuarios/<int:id>/permissoes", methods=["GET", "POST"])
def permissoes(id):

    if session.get("perfil") != "admin":
        return redirect("/menu")

    user = Usuario.query.get_or_404(id)

    if request.method == "POST":
        user.permissoes = json.dumps(request.form.getlist("permissoes"))
        db.session.commit()
        return redirect("/administracao")

    return render_template("permissoes.html", usuario=user)


# ==========================
# CRIAR USUÁRIO
# ==========================
@app.route("/criar-usuario", methods=["POST"])
def criar_usuario():

    if session.get("perfil") != "admin":
        return redirect("/menu")

    perfil = request.form["perfil"]

    permissoes = PERMISSOES_PADRAO if perfil == "admin" else [
        "inventario",
        "movimentacao",
        "consultar"
    ]

    user = Usuario(
        usuario=request.form["usuario"],
        senha=request.form["senha"],
        perfil=perfil,
        permissoes=json.dumps(permissoes)
    )

    db.session.add(user)
    db.session.commit()

    return redirect("/administracao")


# ==========================
# INIT DB
# ==========================
with app.app_context():
    db.create_all()

    admins = Usuario.query.filter_by(perfil="admin").all()
    for admin in admins:
        if not admin.permissoes:
            admin.permissoes = json.dumps(PERMISSOES_PADRAO)

    db.session.commit()


# ==========================
# START
# ==========================
if __name__ == "__main__":
    app.run()
