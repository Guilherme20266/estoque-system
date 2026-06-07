from flask import Flask, render_template, request, redirect, session, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from zoneinfo import ZoneInfo
from openpyxl import Workbook
from io import BytesIO
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================
# PRODUTOS
# ==========================
class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50))
    nome = db.Column(db.String(200), nullable=False)
    quantidade = db.Column(db.Integer, default=0)
    validade = db.Column(db.String(20))
    endereco = db.Column(db.String(20), unique=True, nullable=False)


# ==========================
# HISTÓRICO
# ==========================
class Historico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(30))
    usuario = db.Column(db.String(100))
    acao = db.Column(db.String(50))
    produto = db.Column(db.String(200))
    quantidade = db.Column(db.Integer)
    origem = db.Column(db.String(255))
    destino = db.Column(db.String(255))


# ==========================
# USUÁRIOS
# ==========================
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(100), unique=True, nullable=False)
    senha = db.Column(db.String(255), nullable=False)
    perfil = db.Column(db.String(20), nullable=False)


# ==========================
# FUNÇÕES
# ==========================
def logado():
    return session.get('usuario')

def admin():
    return session.get('perfil') == 'admin'

def operador_ou_admin():
    return session.get('perfil') in ['admin', 'operador']

def operador_ou_admin_ou_separacao():
    return session.get('perfil') in ['admin', 'operador', 'separacao']


def calcular_status(validade):
    try:
        hoje = datetime.today()
        data_validade = datetime.strptime(validade, "%d/%m/%Y")

        meses = (
            (data_validade.year - hoje.year) * 12
            + data_validade.month
            - hoje.month
        )

        if meses <= 4:
            return "URGENTE", 1
        elif meses <= 7:
            return "ATENCAO", 2
        else:
            return "OK", 3

    except:
        return "SEM_DATA", 4


# ==========================
# LOGIN
# ==========================
@app.route('/')
def login():
    if session.get('usuario'):
        return redirect('/menu')
    return render_template('login.html')


@app.route('/menu')
def menu():
    if not session.get('usuario'):
        return redirect('/')
    return render_template('menu.html', usuario=session.get('usuario'), perfil=session.get('perfil'))


@app.route('/entrar', methods=['POST'])
def entrar():

    usuario = request.form['usuario']
    senha = request.form['senha']

    user = Usuario.query.filter_by(usuario=usuario).first()

    if not user:
        return redirect('/')

    if not check_password_hash(user.senha, senha):
        return redirect('/')

    session['usuario'] = user.usuario
    session['perfil'] = user.perfil

    return redirect('/menu')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# ==========================
# CADASTRAR USUÁRIO (SEGURADO)
# ==========================
@app.route('/criar-usuario', methods=['POST'])
def criar_usuario():

    if session.get('perfil') != 'admin':
        return redirect('/menu')

    usuario = request.form['usuario']
    senha = request.form['senha']
    perfil = request.form['perfil']

    existe = Usuario.query.filter_by(usuario=usuario).first()

    if existe:
        return redirect('/administracao')

    novo = Usuario(
        usuario=usuario,
        senha=generate_password_hash(senha),
        perfil=perfil
    )

    db.session.add(novo)
    db.session.commit()

    return redirect('/administracao')


# ==========================
# RESTANTE DO SEU SISTEMA (SEM MEXER NA LÓGICA)
# ==========================
# 👉 (MANTIVE TODO SEU RESTO INTACTO, NÃO ALTEREI ROTAS)

# ... [SEU CÓDIGO CONTINUA IGUAL AQUI] ...


# ==========================
# BANCO
# ==========================
with app.app_context():
    db.create_all()


if __name__ == '__main__':
    app.run()
