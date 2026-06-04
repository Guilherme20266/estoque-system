from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

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
    origem = db.Column(db.String(20))
    destino = db.Column(db.String(20))


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(100), unique=True, nullable=False)
    senha = db.Column(db.String(100), nullable=False)
    perfil = db.Column(db.String(20), nullable=False)

# ==========================
# PERMISSÕES
# ==========================

def logado():
    return session.get('usuario') is not None


def is_admin():
    return session.get('perfil') == 'admin'


def is_operador():
    return session.get('perfil') == 'operador'


def is_separacao():
    return session.get('perfil') == 'separacao'


def pode_consultar():
    return session.get('perfil') in ['admin', 'operador', 'separacao']


def pode_separar():
    return session.get('perfil') in ['admin', 'operador', 'separacao']


def pode_inventario():
    return session.get('perfil') in ['admin', 'operador']


def pode_editar():
    return is_admin()

# ==========================
# STATUS
# ==========================

def calcular_status(validade):
    try:
        hoje = datetime.today()
        data = datetime.strptime(validade, "%d/%m/%Y")

        meses = (data.year - hoje.year) * 12 + data.month - hoje.month

        if meses <= 4:
            return "URGENTE", 1
        elif meses <= 7:
            return "ATENCAO", 2
        return "OK", 3

    except:
        return "SEM_DATA", 4

# ==========================
# LOGIN
# ==========================

@app.route('/')
def login():
    if logado():
        return redirect('/menu')
    return render_template('login.html')


@app.route('/entrar', methods=['POST'])
def entrar():

    user = Usuario.query.filter_by(
        usuario=request.form['usuario'],
        senha=request.form['senha']
    ).first()

    if not user:
        return redirect('/')

    session['usuario'] = user.usuario
    session['perfil'] = user.perfil

    return redirect('/menu')


@app.route('/menu')
def menu():
    if not logado():
        return redirect('/')

    return render_template(
        'menu.html',
        usuario=session['usuario'],
        perfil=session['perfil']
    )


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ==========================
# CADASTRO
# ==========================

@app.route('/cadastrar', methods=['GET', 'POST'])
def cadastrar():

    if not pode_separar() and not is_admin():
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
            data=datetime.now().strftime("%d/%m/%Y %H:%M"),
            usuario=session['usuario'],
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
# INVENTÁRIO
# ==========================

@app.route('/inventario')
def inventario():

    if not logado():
        return redirect('/')

    if not pode_inventario():
        return redirect('/menu')

    produtos = Produto.query.all()

    lista = []

    for p in produtos:
        status, prioridade = calcular_status(p.validade)
        lista.append({
            "produto": p,
            "status": status,
            "prioridade": prioridade
        })

    lista.sort(key=lambda x: x["prioridade"])

    return render_template('inventario.html', lista=lista)

# ==========================
# SEPARAR
# ==========================

@app.route('/separar')
def separar():

    if not pode_separar():
        return redirect('/menu')

    return render_template('separar.html')

# ==========================
# MOVIMENTAÇÃO
# ==========================

@app.route('/movimentacao', methods=['GET', 'POST'])
def movimentacao():

    if not pode_separar() and not is_admin():
        return redirect('/menu')

    produtos = Produto.query.all()

    if request.method == 'POST':

        produto = Produto.query.get(request.form['produto_id'])
        qtd = int(request.form['quantidade'])

        if request.form['acao'] == "entrada":
            produto.quantidade += qtd
        else:
            produto.quantidade -= qtd
            if produto.quantidade <= 0:
                db.session.delete(produto)

        db.session.add(Historico(
            data=datetime.now().strftime("%d/%m/%Y %H:%M"),
            usuario=session['usuario'],
            acao=request.form['acao'].upper(),
            produto=produto.nome,
            quantidade=qtd,
            origem=produto.endereco,
            destino=produto.endereco
        ))

        db.session.commit()

        return redirect('/movimentacao')

    return render_template('movimentacao.html', produtos=produtos)

# ==========================
# TRANSFERÊNCIA
# ==========================

@app.route('/transferencia', methods=['GET', 'POST'])
def transferencia():

    if not pode_separar() and not is_admin():
        return redirect('/menu')

    produtos = Produto.query.all()

    if request.method == 'POST':

        produto = Produto.query.get(request.form['produto_id'])
        novo = request.form['novo_endereco']

        if Produto.query.filter_by(endereco=novo).first():
            return "Endereço ocupado"

        antigo = produto.endereco
        produto.endereco = novo

        db.session.add(Historico(
            data=datetime.now().strftime("%d/%m/%Y %H:%M"),
            usuario=session['usuario'],
            acao="TRANSFERENCIA",
            produto=produto.nome,
            quantidade=produto.quantidade,
            origem=antigo,
            destino=novo
        ))

        db.session.commit()

        return redirect('/inventario')

    return render_template('transferencia.html', produtos=produtos)

# ==========================
# CONSULTA + HISTÓRICO
# ==========================

@app.route('/consulta')
def consulta():

    if not logado():
        return redirect('/')

    produtos = Produto.query.all()

    lista = []

    for p in produtos:
        status, prioridade = calcular_status(p.validade)
        lista.append({
            "produto": p,
            "status": status,
            "prioridade": prioridade
        })

    return render_template('consulta.html', lista=lista)


@app.route('/historico')
def historico():

    if not pode_consultar():
        return redirect('/menu')

    registros = Historico.query.order_by(Historico.id.desc()).all()

    return render_template('historico.html', registros=registros)

# ==========================
# EDITAR
# ==========================

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):

    if not is_admin():
        return redirect('/menu')

    produto = Produto.query.get_or_404(id)

    if request.method == 'POST':
        produto.nome = request.form['nome']
        produto.codigo = request.form['codigo']
        produto.validade = request.form['validade']
        db.session.commit()
        return redirect('/inventario')

    return render_template('editar.html', produto=produto)

# ==========================
# ADMIN
# ==========================

@app.route('/administracao')
def administracao():

    if not is_admin():
        return redirect('/menu')

    usuarios = Usuario.query.all()

    return render_template('administracao.html', usuarios=usuarios)

@app.route('/criar-usuario', methods=['POST'])
def criar_usuario():

    if not is_admin():
        return redirect('/menu')

    db.session.add(Usuario(
        usuario=request.form['usuario'],
        senha=request.form['senha'],
        perfil=request.form['perfil']
    ))

    db.session.commit()

    return redirect('/administracao')

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

# ==========================
# RUN
# ==========================

if __name__ == '__main__':
    app.run()
