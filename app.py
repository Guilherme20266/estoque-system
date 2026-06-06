from flask import Flask, render_template, request, redirect, session, flash, Response
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
# REDIRECT INICIAL
# ==========================
@app.route('/')
def index():
    if session.get('usuario'):
        return redirect('/menu')
    return redirect('/login')


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

def operador():
    return session.get('perfil') in ['admin', 'operador', 'separacao']


# ==========================
# LOGIN / LOGOUT / MENU
# ==========================
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


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


@app.route('/menu')
def menu():
    if not logado():
        return redirect('/login')

    return render_template(
        'menu.html',
        usuario=session.get('usuario'),
        perfil=session.get('perfil')
    )


# ==========================
# CADASTRAR
# ==========================
@app.route('/cadastrar', methods=['GET', 'POST'])
def cadastrar():
    if not operador():
        return redirect('/menu')

    if request.method == 'POST':

        endereco = f"{request.form['rua']}-{request.form['coluna']}-{request.form['nivel']}"

        existe = Produto.query.filter_by(endereco=endereco).first()
        if existe:
            return redirect('/cadastrar?erro=endereco')

        produto = Produto(
            codigo=request.form['codigo'],
            nome=request.form['nome'],
            quantidade=int(request.form['quantidade']),
            validade=request.form['validade'],
            endereco=endereco
        )

        db.session.add(produto)

        db.session.add(Historico(
            data=datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
            usuario=session.get('usuario'),
            acao="CADASTRO",
            produto=produto.nome,
            quantidade=produto.quantidade,
            origem="-",
            destino=endereco
        ))

        db.session.commit()

        return redirect('/cadastrar?sucesso=1')

    return render_template('cadastrar.html')


# ==========================
# CONSULTA
# ==========================
@app.route('/consulta')
def consulta():
    if not logado():
        return redirect('/login')

    busca = request.args.get('busca', '')
    produtos = Produto.query.all()

    if busca:
        produtos = [
            p for p in produtos
            if busca.lower() in (p.nome or "").lower()
            or busca.lower() in (p.codigo or "").lower()
            or busca.lower() in (p.endereco or "").lower()
        ]

    lista = [{"produto": p, "status": "OK", "prioridade": 1} for p in produtos]

    return render_template('consulta.html', lista=lista, busca=busca)


# ==========================
# INVENTÁRIO
# ==========================
@app.route('/inventario')
def inventario():
    if not logado():
        return redirect('/login')

    produtos = Produto.query.all()

    lista = [{"produto": p, "status": "OK", "prioridade": 1} for p in produtos]

    return render_template('inventario.html', lista=lista)


# ==========================
# HISTÓRICO
# ==========================
@app.route('/historico')
def historico():
    if not operador():
        return redirect('/menu')

    registros = Historico.query.order_by(Historico.id.desc()).all()

    return render_template('historico.html', registros=registros)


# ==========================
# MOVIMENTAÇÃO
# ==========================
@app.route('/movimentacao', methods=['GET', 'POST'])
def movimentacao():
    if not operador():
        return redirect('/menu')

    busca = request.args.get('busca', '')
    produtos = Produto.query.all()

    if busca:
        produtos = [p for p in produtos if busca.lower() in p.nome.lower()]

    if request.method == 'POST':

        produto = Produto.query.get(request.form['produto_id'])
        acao = request.form['acao']
        qtd = int(request.form['quantidade'])

        if acao == "entrada":
            produto.quantidade += qtd

        elif acao == "saida":
            produto.quantidade -= qtd

        db.session.add(Historico(
            data=datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
            usuario=session.get('usuario'),
            acao=acao.upper(),
            produto=produto.nome,
            quantidade=qtd,
            origem=produto.endereco,
            destino=produto.endereco
        ))

        if produto.quantidade <= 0:
            db.session.delete(produto)

        db.session.commit()
        return redirect('/movimentacao')

    return render_template('movimentacao.html', produtos=produtos, busca=busca)


# ==========================
# ADMIN
# ==========================
@app.route('/administracao')
def administracao():
    if not admin():
        return redirect('/menu')

    usuarios = Usuario.query.all()

    return render_template(
        'administracao.html',
        usuarios=usuarios,
        total_produtos=Produto.query.count(),
        total_enderecos=Produto.query.count(),
        total_historico=Historico.query.count()
    )


# ==========================
# RANKING (OK)
# ==========================
@app.route('/ranking-usuarios')
def ranking_usuarios():
    if not operador():
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
# INIT DB
# ==========================
with app.app_context():
    db.create_all()

    if not Usuario.query.filter_by(usuario='admin').first():
        db.session.add(Usuario(
            usuario='admin',
            senha='10080810',
            perfil='admin'
        ))
        db.session.commit()


if __name__ == '__main__':
    app.run()
