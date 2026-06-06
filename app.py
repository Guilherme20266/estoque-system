from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from zoneinfo import ZoneInfo
from openpyxl import Workbook
from io import BytesIO

app = Flask(__name__)

app.secret_key = "estoque_super_secreto_2026"

app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://automatico:yC0t7wVgQ2ozXUMfhtdUT8l4FZue9HW3@dpg-d8fpjbv7f7vs73ejl8sg-a.oregon-postgres.render.com/estoque_zd9a"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================
# MODELOS
# ==========================
class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50))
    nome = db.Column(db.String(200), nullable=False)
    quantidade = db.Column(db.Integer, default=0)
    validade = db.Column(db.String(20))
    endereco = db.Column(db.String(20), unique=True, nullable=False)


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
    usuario = db.Column(db.String(100), unique=True, nullable=False)
    senha = db.Column(db.String(100), nullable=False)
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

# ==========================
# LOGIN / MENU
# ==========================
@app.route('/')
def home():
    if logado():
        return redirect('/menu')
    return redirect('/login')


@app.route('/login')
def login():
    return render_template('login.html')


@app.route('/entrar', methods=['POST'])
def entrar():
    usuario = request.form['usuario']
    senha = request.form['senha']

    user = Usuario.query.filter_by(usuario=usuario, senha=senha).first()

    if not user:
        return redirect('/login')

    session['usuario'] = user.usuario
    session['perfil'] = user.perfil

    return redirect('/menu')


@app.route('/menu')
def menu():
    if not logado():
        return redirect('/login')

    return render_template(
        'menu.html',
        usuario=session.get('usuario'),
        perfil=session.get('perfil')
    )


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ==========================
# MOVIMENTAÇÃO (SEU ORIGINAL OK)
# ==========================
@app.route('/movimentacao', methods=['GET', 'POST'])
def movimentacao():

    if not operador_ou_admin_ou_separacao():
        return redirect('/menu')

    busca = request.args.get("busca", "")
    produtos = Produto.query.all()

    if busca:
        produtos = [
            p for p in produtos
            if busca.lower() in (p.nome or "").lower()
            or busca.lower() in (p.codigo or "").lower()
            or busca.lower() in (p.endereco or "").lower()
        ]

    if request.method == 'POST':

        produto_id = request.form['produto_id']
        acao = request.form['acao']
        quantidade = int(request.form['quantidade'])

        usuario = session.get('usuario')

        produto = Produto.query.get(produto_id)

        if not produto:
            return redirect('/movimentacao')

        if acao == "entrada":
            produto.quantidade += quantidade

        if acao == "saida":
            produto.quantidade -= quantidade

        historico = Historico(
            data=datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
            usuario=usuario,
            acao=acao.upper(),
            produto=produto.nome,
            quantidade=quantidade,
            origem=produto.endereco,
            destino=produto.endereco if acao == "entrada" else "-"
        )

        db.session.add(historico)

        if produto.quantidade <= 0:
            db.session.delete(produto)

        db.session.commit()

        return redirect('/movimentacao')

    return render_template('movimentacao.html', produtos=produtos, busca=busca)

# ==========================
# RANKING (OK)
# ==========================
@app.route('/ranking-usuarios')
def ranking():

    if not operador_ou_admin():
        return redirect('/menu')

    dados = db.session.query(
        Historico.usuario,
        db.func.sum(Historico.quantidade).label('total')
    ).filter(
        Historico.acao == "SAIDA"
    ).group_by(
        Historico.usuario
    ).order_by(
        db.desc('total')
    ).all()

    return render_template('ranking.html', dados=dados)

# ==========================
# INIT
# ==========================
with app.app_context():
    db.create_all()

    admin_user = Usuario.query.filter_by(usuario='admin').first()

    if not admin_user:
        db.session.add(Usuario(
            usuario='admin',
            senha='10080810',
            perfil='admin'
        ))
        db.session.commit()

if __name__ == '__main__':
    app.run()
