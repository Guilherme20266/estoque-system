from flask import Flask, render_template, request, redirect, session, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from zoneinfo import ZoneInfo
from openpyxl import Workbook
from io import BytesIO

import os

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "teste123456789"
)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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

    endereco = db.Column(
        db.String(20),
        unique=True,
        nullable=False
    )


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

    usuario = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    senha = db.Column(
        db.String(100),
        nullable=False
    )

    perfil = db.Column(
        db.String(20),
        nullable=False
    )


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

        data_validade = datetime.strptime(
            validade,
            "%d/%m/%Y"
        )

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
# MENU
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

    return render_template(
        'menu.html',
        usuario=session.get('usuario'),
        perfil=session.get('perfil')
    )

@app.route('/entrar', methods=['POST'])
def entrar():

    usuario = request.form['usuario']
    senha = request.form['senha']

    user = Usuario.query.filter_by(
        usuario=usuario,
        senha=senha
    ).first()

    if not user:
        return redirect('/')

    session['usuario'] = user.usuario
    session['perfil'] = user.perfil

    return redirect('/menu')

@app.route('/logout')
def logout():

    session.clear()

    return redirect('/')


# ==========================
# CADASTRAR
# ==========================
@app.route('/cadastrar', methods=['GET', 'POST'])
def cadastrar():

    if not operador_ou_admin_ou_separacao():
        return redirect('/menu')

    if request.method == 'POST':

        endereco = (
            f"{request.form['rua']}-"
            f"{request.form['coluna']}-"
            f"{request.form['nivel']}"
        )

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

        historico = Historico(
            data=datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
            usuario=session.get('usuario'),
            acao="CADASTRO",
            produto=produto.nome,
            quantidade=produto.quantidade,
            origem="-",
            destino=endereco
        )

        db.session.add(historico)

        db.session.commit()

        return redirect('/cadastrar?sucesso=1')

    return render_template('cadastrar.html')

# ==========================
# INVENTÁRIO
# ==========================
@app.route('/inventario')
def inventario():

    if not operador_ou_admin_ou_separacao():
        return redirect('/')

    produtos = Produto.query.all()

    lista = []

    for produto in produtos:

        status, prioridade = calcular_status(
            produto.validade
        )

        lista.append({
            "produto": produto,
            "status": status,
            "prioridade": prioridade
        })

    lista.sort(key=lambda x: x["prioridade"])

    return render_template(
        'inventario.html',
        lista=lista
    )

# ==========================
# EDITAR PRODUTO
# ==========================
@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):

    if not operador_ou_admin_ou_separacao():
        return redirect('/menu')

    produto = Produto.query.get_or_404(id)

    if request.method == 'POST':

        nome_antigo = produto.nome
        codigo_antigo = produto.codigo
        validade_antiga = produto.validade

        novo_nome = request.form['nome']
        novo_codigo = request.form['codigo']
        nova_validade = request.form['validade']

        produto.nome = novo_nome
        produto.codigo = novo_codigo
        produto.validade = nova_validade

        historico = Historico(
            data=datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
            usuario=session.get('usuario'),
            acao="EDITAR",
            produto=novo_nome,
            quantidade=produto.quantidade,
            origem=f"{nome_antigo} | {codigo_antigo} | {validade_antiga}",
            destino=f"{novo_nome} | {novo_codigo} | {nova_validade}"
        )

        db.session.add(historico)
        db.session.commit()

        flash("Produto editado com sucesso!", "success")

        return redirect('/inventario')

    return render_template('editar.html', produto=produto)
# ==========================
# MOVIMENTAÇÃO
# ==========================
@app.route('/movimentacao', methods=['GET', 'POST'])
def movimentacao():

    if not operador_ou_admin_ou_separacao():
        return redirect('/menu')

    busca = request.args.get("busca", "")
    produto_id_url = request.args.get("produto_id")

    produtos = Produto.query.all()

    produto_selecionado = None

    if produto_id_url:
        produto_selecionado = Produto.query.get(produto_id_url)

    # 🔥 se veio produto direto, trava na tela dele
    if produto_selecionado:
        produtos = [produto_selecionado]

    if busca:

        produtos = [
            p for p in produtos
            if busca.lower() in p.nome.lower()
            or busca.lower() in p.codigo.lower()
            or busca.lower() in p.endereco.lower()
        ]

    if request.method == 'POST':

        produto_id = request.form.get('produto_id') or request.args.get('produto_id')

        acao = request.form['acao']
        quantidade = int(request.form['quantidade'])

        produto = Produto.query.get(produto_id)

        if not produto:
            return redirect('/movimentacao')

        if acao == "entrada":

            produto.quantidade += quantidade

            db.session.add(Historico(
                data=datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
                usuario=session.get('usuario'),
                acao="ENTRADA",
                produto=produto.nome,
                quantidade=quantidade,
                origem=produto.endereco,
                destino=produto.endereco
            ))

            db.session.commit()
            return redirect('/movimentacao?sucesso=entrada')

        if acao == "saida":

            produto.quantidade -= quantidade

            db.session.add(Historico(
                data=datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
                usuario=session.get('usuario'),
                acao="SAIDA",
                produto=produto.nome,
                quantidade=quantidade,
                origem=produto.endereco,
                destino="-"
            ))

            if produto.quantidade <= 0:
                db.session.delete(produto)
                db.session.commit()
                return redirect('/movimentacao?sucesso=zerado')

            db.session.commit()
            return redirect('/movimentacao?sucesso=saida')

    return render_template(
        'movimentacao.html',
        produtos=produtos,
        busca=busca,
        produto_selecionado=produto_selecionado
    )

# ==========================
# TRANSFERÊNCIA
# ==========================
@app.route('/transferencia', methods=['GET', 'POST'])
def transferencia():

    if not operador_ou_admin_ou_separacao():
        return redirect('/menu')

    busca = request.args.get("busca", "")
    produto_id_url = request.args.get("produto_id")

    produtos = Produto.query.all()

    produto_selecionado = None

    if produto_id_url:
        produto_selecionado = Produto.query.get(produto_id_url)

    # 🔥 trava no produto se veio da tela anterior
    if produto_selecionado:
        produtos = [produto_selecionado]

    if busca:

        produtos = [
            p for p in produtos
            if busca.lower() in p.nome.lower()
            or busca.lower() in p.codigo.lower()
            or busca.lower() in p.endereco.lower()
        ]

    if request.method == 'POST':

        produto_id = request.form.get('produto_id') or request.args.get('produto_id')

        produto = Produto.query.get(produto_id)

        if not produto:
            return redirect('/transferencia')

        novo_endereco = request.form['novo_endereco']

        existe = Produto.query.filter_by(endereco=novo_endereco).first()

        if existe:
            flash("Endereço já está ocupado", "error")
            return redirect('/transferencia')

        endereco_antigo = produto.endereco
        produto.endereco = novo_endereco

        db.session.add(Historico(
            data=datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
            usuario=session.get('usuario'),
            acao="TRANSFERENCIA",
            produto=produto.nome,
            quantidade=produto.quantidade,
            origem=endereco_antigo,
            destino=novo_endereco
        ))

        db.session.commit()

        flash(f"Transferência concluída! Novo endereço: {novo_endereco}", "success")

        return redirect('/transferencia?produto_id=' + str(produto.id))

    return render_template(
        'transferencia.html',
        produtos=produtos,
        busca=busca,
        produto_selecionado=produto_selecionado
    )
# ==========================
# HISTÓRICO
# ==========================
@app.route('/historico')
def historico():

    if not operador_ou_admin():
        return redirect('/menu')

    busca = request.args.get('busca', '')

    registros = Historico.query.order_by(
        Historico.id.desc()
    ).all()

    if busca:

        registros = [

            r for r in registros

            if busca.lower() in (r.usuario or '').lower()
            or busca.lower() in (r.produto or '').lower()
            or busca.lower() in (r.data or '').lower()
            or busca.lower() in (r.origem or '').lower()
            or busca.lower() in (r.destino or '').lower()

        ]

    return render_template(
        'historico.html',
        registros=registros,
        busca=busca
    )

# ==========================
# CONSULTA
# ==========================
@app.route('/consulta')
def consulta():

    if not logado():
        return redirect('/')

    busca = request.args.get('busca', '')

    produtos = Produto.query.all()

    if busca:

        produtos = [
            p for p in produtos
            if busca.lower() in p.nome.lower()
            or busca.lower() in p.codigo.lower()
            or busca.lower() in p.endereco.lower()
        ]

    lista = []

    for produto in produtos:

        status, prioridade = calcular_status(produto.validade)

        lista.append({
            "produto": produto,
            "status": status,
            "prioridade": prioridade
        })

    lista.sort(key=lambda x: x["prioridade"])

    return render_template(
        'consulta.html',
        lista=lista,
        busca=busca
    )
    # ==========================
    # HISTÓRICO DE CONSULTA
    # ==========================
    if busca and len(produtos) > 0:

        historico = Historico(
            data=datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
            usuario=session.get('usuario'),
            acao="CONSULTA",
            produto=busca,
            quantidade=len(produtos),
            origem="-",
            destino="-"
        )

        db.session.add(historico)
        db.session.commit()

    return render_template(
        'consulta.html',
        lista=lista,
        busca=busca
    )

# ==========================
# EXPORTAR EXCEL - CONSULTA
# ==========================
@app.route('/exportar-consulta')
def exportar_consulta():

    if not logado():
        return redirect('/')

    busca = request.args.get('busca', '')

    produtos = Produto.query.all()

    if busca:
        produtos = [
            p for p in produtos
            if busca.lower() in p.nome.lower()
            or busca.lower() in p.codigo.lower()
            or busca.lower() in p.endereco.lower()
        ]

    wb = Workbook()
    ws = wb.active
    ws.title = "Consulta"

    ws.append(["Nome", "Código", "Quantidade", "Validade", "Endereço"])

    for p in produtos:
        ws.append([
            p.nome,
            p.codigo,
            p.quantidade,
            p.validade,
            p.endereco
        ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return Response(
        output.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=consulta.xlsx"
        }
    )

@app.route('/excluir/<int:id>')
def excluir(id):

    produto = Produto.query.get_or_404(id)

    historico = Historico(
        data=datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
        usuario=session.get('usuario'),
        acao="EXCLUSAO",
        produto=produto.nome,
        quantidade=produto.quantidade,
        origem=produto.endereco,
        destino="-"
    )

    db.session.add(historico)
    db.session.delete(produto)
    db.session.commit()

    flash("Produto excluído com sucesso!", "success")

    return redirect('/inventario')
# ==========================
# ADMINISTRAÇÃO
# ==========================
@app.route('/administracao')
def administracao():

    if session.get('perfil') != 'admin':
        return redirect('/menu')

    # ==========================
    # ESTATÍSTICAS GERAIS
    # ==========================
    total_produtos = Produto.query.count()
    total_enderecos = Produto.query.count()
    total_historico = Historico.query.count()
    total_usuarios = Usuario.query.count()

    produtos_urgentes = sum(
        1 for p in Produto.query.all()
        if calcular_status(p.validade)[0] == "URGENTE"
    )

    ultimo_historico = Historico.query.order_by(
        Historico.id.desc()
    ).first()

    # ==========================
    # MASTER
    # ==========================
    master = Usuario.query.filter_by(
        usuario="Guilherme$"
    ).first()

    # ==========================
    # USUÁRIOS (SEM MASTER)
    # ==========================
    usuarios = Usuario.query.filter(
        Usuario.usuario != "Guilherme$"
    ).order_by(
        Usuario.usuario.asc()
    ).all()

    # ==========================
    # DEBUG (opcional)
    # ==========================
    for u in usuarios:
        print(
            "ID:", u.id,
            "USUARIO:", u.usuario,
            "SENHA:", u.senha,
            "PERFIL:", u.perfil
        )

    # ==========================
    # RENDER
    # ==========================
    return render_template(
        'administracao.html',
        total_produtos=total_produtos,
        total_enderecos=total_enderecos,
        total_historico=total_historico,
        total_usuarios=total_usuarios,
        produtos_urgentes=produtos_urgentes,
        ultimo_historico=ultimo_historico,
        usuarios=usuarios,
        master=master
    )

@app.route('/criar-usuario', methods=['POST'])
def criar_usuario():

    if session.get('perfil') != 'admin':
        return redirect('/menu')

    usuario = request.form['usuario']
    senha = request.form['senha']
    perfil = request.form['perfil']

    existe = Usuario.query.filter_by(
        usuario=usuario
    ).first()

    if existe:
        return redirect('/administracao')

    novo = Usuario(
        usuario=usuario,
        senha=senha,
        perfil=perfil
    )

    db.session.add(novo)
    db.session.commit()

    return redirect('/administracao')


@app.route('/excluir-usuario/<int:id>')
def excluir_usuario(id):

    if session.get('perfil') != 'admin':
        return redirect('/menu')

    usuario = Usuario.query.get_or_404(id)

    # bloqueia o master
    if usuario.usuario == "Guilherme$":
        return redirect('/administracao')

    db.session.delete(usuario)
    db.session.commit()

    return redirect('/administracao')

@app.route('/editar-usuario/<int:id>', methods=['GET', 'POST'])
def editar_usuario(id):

    if session.get('perfil') != 'admin':
        return redirect('/menu')

    usuario = Usuario.query.get_or_404(id)

    if request.method == 'POST':

        nova_senha = request.form['senha']
        novo_perfil = request.form['perfil']

        usuario.senha = nova_senha
        usuario.perfil = novo_perfil

        db.session.commit()

        return redirect('/administracao')

    return render_template('editar_usuario.html', usuario=usuario)

@app.route('/limpar-historico')
def limpar_historico():

    if session.get('perfil') != 'admin':
        return redirect('/menu')

    Historico.query.delete()

    db.session.commit()

    return redirect('/administracao')

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run()
