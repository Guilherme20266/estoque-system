from flask import Flask, render_template, request, redirect, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from zoneinfo import ZoneInfo

app = Flask(__name__)

app.secret_key = "estoque_super_secreto_2026"

app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://automatico:yC0t7wVgQ2ozXUMfhtdUT8l4FZue9HW3@dpg-d8fpjbv7f7vs73ejl8sg-a.oregon-postgres.render.com/estoque_zd9a"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ==========================
# REDIRECT
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


def calcular_status(validade):

    try:
        hoje = datetime.today()
        data = datetime.strptime(validade, "%d/%m/%Y")

        meses = (data.year - hoje.year) * 12 + (data.month - hoje.month)

        if meses <= 4:
            return "URGENTE", 3
        elif meses <= 7:
            return "ATENCAO", 2
        else:
            return "OK", 1

    except:
        return "SEM_DATA", 0


# ==========================
# LOGIN
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

    return render_template('menu.html',
                           usuario=session.get('usuario'),
                           perfil=session.get('perfil'))


# ==========================
# CADASTRO
# ==========================
@app.route('/cadastrar', methods=['GET', 'POST'])
def cadastrar():
    if not operador():
        return redirect('/menu')

    if request.method == 'POST':

        endereco = f"{request.form['rua']}-{request.form['coluna']}-{request.form['nivel']}"

        if Produto.query.filter_by(endereco=endereco).first():
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
# CONSULTA (CORRIGIDA)
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

    lista = []

    for p in produtos:

        status, prioridade = calcular_status(p.validade)

        lista.append({
            "produto": p,
            "status": status,
            "prioridade": prioridade
        })

    # 🔥 CORREÇÃO FINAL (URGENTE NO TOPO)
    lista.sort(key=lambda x: x["prioridade"], reverse=True)

    return render_template('consulta.html', lista=lista, busca=busca)


# ==========================
# INVENTÁRIO
# ==========================
@app.route('/inventario')
def inventario():

    if not logado():
        return redirect('/login')

    produtos = Produto.query.all()

    lista = []

    for p in produtos:
        status, prioridade = calcular_status(p.validade)
        lista.append({"produto": p, "status": status, "prioridade": prioridade})

    lista.sort(key=lambda x: x["prioridade"], reverse=True)

    return render_template('inventario.html', lista=lista)


# ==========================
# HISTÓRICO
# ==========================
@app.route('/historico')
def historico():

    if not operador():
        return redirect('/menu')

    busca = request.args.get('busca', '')

    registros = Historico.query.order_by(Historico.id.desc()).all()

    lista = []

    for r in registros:

        if busca:
            if busca.lower() not in (r.usuario or '').lower() and \
               busca.lower() not in (r.produto or '').lower() and \
               busca.lower() not in (r.data or '').lower():
                continue

        lista.append({"registro": r})

    return render_template('historico.html', lista=lista, busca=busca)


# ==========================
# ADMIN
# ==========================
@app.route('/administracao')
def administracao():

    if not admin():
        return redirect('/menu')

    return render_template(
        'administracao.html',
        usuarios=Usuario.query.all(),
        total_produtos=Produto.query.count(),
        total_enderecos=Produto.query.count(),
        total_historico=Historico.query.count()
    )


# ==========================
# RANKING
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
