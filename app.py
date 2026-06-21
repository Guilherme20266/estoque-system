from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    redirect,
    session,
    url_for,
    flash,
    Response,
    send_file
)

from flask_sqlalchemy import SQLAlchemy

from datetime import (
    datetime,
    timedelta
)

from zoneinfo import ZoneInfo

from openpyxl import Workbook

from io import BytesIO

import io
import os
import json

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

app = Flask(__name__)

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=20)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "teste123456789"
)
db_url = os.getenv("DATABASE_URL")

if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url

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
# CatalogoProduto
# ==========================
class CatalogoProduto(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    codigo = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    nome = db.Column(
        db.String(200),
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

    permissoes = db.Column(
        db.Text,
        default="[]"
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


# ==========================
# PERMISSÕES
# ==========================

def tem_permissao(permissao):

    # Admin sempre tem acesso total
    if session.get("perfil") == "admin":
        return True

    usuario = Usuario.query.filter_by(
        usuario=session.get("usuario")
    ).first()

    if not usuario:
        return False

    try:
        permissoes = json.loads(usuario.permissoes or "[]")
    except:
        permissoes = []

    return permissao in permissoes


# ==========================
# STATUS DA VALIDADE
# ==========================

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


@app.route('/buscar-produto/<codigo>')
def buscar_produto(codigo):

    produto = CatalogoProduto.query.filter_by(
        codigo=codigo
    ).first()

    if produto:
        return jsonify({
            "encontrado": True,
            "nome": produto.nome
        })

    return jsonify({
        "encontrado": False
    })


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

    session.permanent = True
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

        existe = Produto.query.filter_by(
            endereco=endereco
        ).first()

        if existe:
            return redirect('/cadastrar?erro=endereco')

        # SALVA NO CATÁLOGO
        catalogo = CatalogoProduto.query.filter_by(
            codigo=request.form['codigo']
        ).first()

        if not catalogo:
            catalogo = CatalogoProduto(
                codigo=request.form['codigo'],
                nome=request.form['nome']
            )
            db.session.add(catalogo)

        # ==========================
        # VALIDAÇÃO DE QUANTIDADE
        # ==========================
        try:
            quantidade = int(request.form['quantidade'])
        except:
            return redirect('/cadastrar?erro=quantidade')

        if quantidade < 1 or quantidade > 1000:
            return redirect('/cadastrar?erro=quantidade')

        produto = Produto(
            codigo=request.form['codigo'],
            nome=request.form['nome'],
            quantidade=quantidade,
            validade=request.form['validade'],
            endereco=endereco
        )

        db.session.add(produto)

        historico = Historico(
            data=datetime.now(
                ZoneInfo("America/Sao_Paulo")
            ).strftime("%d/%m/%Y %H:%M"),
            usuario=session.get('usuario'),
            acao="CADASTRO",
            produto=produto.nome,
            quantidade=quantidade,
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
        
        catalogo = CatalogoProduto.query.filter_by(
            codigo=novo_codigo
        ).first()

        if catalogo:
            catalogo.nome = novo_nome

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
            return redirect('/movimentacao')

        acao = request.form['acao']
        quantidade = int(request.form['quantidade'])

        # ==========================
        # ENTRADA
        # ==========================
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

            flash(f"✔ Entrada: +{quantidade} unidades em {produto.endereco}", "success")

            return redirect('/movimentacao?produto_id=' + str(produto.id))

        # ==========================
        # SAÍDA
        # ==========================
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

            # 🔥 SE ZEROU OU MENOR QUE ZERO
            if produto.quantidade <= 0:

                nome = produto.nome
                endereco = produto.endereco

                db.session.delete(produto)
                db.session.commit()

                flash(f"🚨 ESTOQUE ZERADO: {nome} removido do endereço {endereco}", "error")

                return redirect('/movimentacao')

            db.session.commit()

            flash(f"✔ Saída: -{quantidade} unidades de {produto.endereco}", "success")

            return redirect('/movimentacao?produto_id=' + str(produto.id))

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

        flash(f"✔ Transferência realizada com sucesso. Novo endereço: {novo_endereco}", "success")

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
# EXPORTAR HISTÓRICO EXCEL
# ==========================

@app.route('/exportar-historico')
def exportar_historico():

    if session.get('perfil') != 'admin':
        return redirect('/menu')

    historico = Historico.query.order_by(Historico.id.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Historico"

    ws.append(["Data", "Usuário", "Ação", "Produto", "Quantidade", "Origem", "Destino"])

    for h in historico:
        ws.append([
            h.data,
            h.usuario,
            h.acao,
            h.produto,
            h.quantidade,
            h.origem,
            h.destino
        ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return Response(
        output.read(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=historico.xlsx"
        }
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

    # ==========================
    # HISTÓRICO DE CONSULTA
    # ==========================
    if busca and len(produtos) > 0:

        db.session.add(Historico(
            data=datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
            usuario=session.get('usuario'),
            acao="CONSULTA",
            produto=busca,
            quantidade=len(produtos),
            origem="-",
            destino="-"
        ))

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

@app.route('/usuarios/<int:id>/permissoes', methods=['GET', 'POST'])
def permissoes(id):

    if session.get('perfil') != 'admin':
        return redirect('/menu')

    usuario = Usuario.query.get_or_404(id)

    if request.method == 'POST':

        permissoes = request.form.getlist('permissoes')

        usuario.permissoes = json.dumps(permissoes)

        db.session.commit()

        return redirect('/administracao')

    permissoes_usuario = json.loads(usuario.permissoes or "[]")

    return render_template(
        'permissoes.html',
        usuario=usuario,
        permissoes_usuario=permissoes_usuario
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

# ==========================
# CATÁLOGO DE PRODUTOS
# ==========================
@app.route('/catalogo')
def catalogo():

    if session.get('perfil') != 'admin':
        return redirect('/menu')

    busca = request.args.get('busca', '')

    produtos = CatalogoProduto.query.order_by(
        CatalogoProduto.nome.asc()
    ).all()

    if busca:
        produtos = [
            p for p in produtos
            if busca.lower() in p.nome.lower()
            or busca.lower() in p.codigo.lower()
        ]

    return render_template(
        'catalogo.html',
        produtos=produtos,
        busca=busca
    )

# ==========================
# EDITAR CATÁLOGO
# ==========================
@app.route('/editar-catalogo/<int:id>', methods=['GET', 'POST'])
def editar_catalogo(id):

    if session.get('perfil') != 'admin':
        return redirect('/menu')

    catalogo = CatalogoProduto.query.get_or_404(id)

    if request.method == 'POST':

        novo_codigo = request.form.get('codigo', '').strip()
        novo_nome = request.form.get('nome', '').strip()

        if not novo_codigo or not novo_nome:
            return redirect(url_for('editar_catalogo', id=id, erro=1))

        try:
            codigo_antigo = catalogo.codigo

            # atualiza catálogo
            catalogo.codigo = novo_codigo
            catalogo.nome = novo_nome

            # atualiza produtos vinculados
            produtos = Produto.query.filter_by(codigo=codigo_antigo).all()

            for p in produtos:
                p.codigo = novo_codigo
                p.nome = novo_nome

            db.session.commit()

            return redirect(url_for('editar_catalogo', id=id, ok=1))

        except Exception:
            db.session.rollback()
            return redirect(url_for('editar_catalogo', id=id, erro=1))

    return render_template(
        'editar_catalogo.html',
        catalogo=catalogo,
        ok=request.args.get('ok'),
        erro=request.args.get('erro')
    )

@app.route('/excluir-catalogo/<int:id>')
def excluir_catalogo(id):

    if session.get('perfil') != 'admin':
        return redirect('/menu')

    catalogo = CatalogoProduto.query.get_or_404(id)

    # remove produtos vinculados (opcional, mas recomendado)
    produtos = Produto.query.filter_by(codigo=catalogo.codigo).all()

    for p in produtos:
        db.session.delete(p)

    db.session.delete(catalogo)
    db.session.commit()

    return redirect('/catalogo')

@app.route('/limpar-historico', methods=['POST'])
def limpar_historico():

    if session.get('perfil') != 'admin':
        return redirect('/menu')

    Historico.query.delete()
    db.session.commit()

    flash("Histórico apagado com sucesso!", "success")
    return redirect('/administracao')

@app.route('/criar-backup')
def criar_backup():

    if session.get('perfil') != 'admin':
        return redirect('/menu')

    backup = {

        "produtos": [
            {
                "codigo": p.codigo,
                "nome": p.nome,
                "quantidade": p.quantidade,
                "validade": p.validade,
                "endereco": p.endereco
            }
            for p in Produto.query.all()
        ],

        "catalogo": [
            {
                "codigo": c.codigo,
                "nome": c.nome
            }
            for c in CatalogoProduto.query.all()
        ],

        "historico": [
            {
                "data": h.data,
                "usuario": h.usuario,
                "acao": h.acao,
                "produto": h.produto,
                "quantidade": h.quantidade,
                "origem": h.origem,
                "destino": h.destino
            }
            for h in Historico.query.all()
        ],

        "usuarios": [
            {
                "usuario": u.usuario,
                "senha": u.senha,
                "perfil": u.perfil
            }
            for u in Usuario.query.all()
        ]

    }

    pasta = "backups"
    os.makedirs(pasta, exist_ok=True)

    nome_arquivo = datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).strftime("backup_%Y%m%d_%H%M%S.json")

    caminho = os.path.join(pasta, nome_arquivo)

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(
            backup,
            f,
            ensure_ascii=False,
            indent=4
        )

    try:
        enviar_backup_drive(caminho)

        flash(
            "Backup criado e enviado ao Google Drive com sucesso!",
            "success"
        )

    except Exception as e:
        print(e)

        flash(
            f"Erro ao enviar backup: {e}",
            "error"
        )

    return redirect('/administracao')
@app.route('/baixar-backup')
def baixar_backup():

    if session.get('perfil') != 'admin':
        return redirect('/menu')

    pasta = "backups"

    if not os.path.exists(pasta):
        return redirect('/administracao')

    arquivos = sorted(
        os.listdir(pasta),
        reverse=True
    )

    if not arquivos:
        return redirect('/administracao')

    ultimo = os.path.join(
        pasta,
        arquivos[0]
    )

    return send_file(
        ultimo,
        as_attachment=True
    )

@app.route('/backup-automatico')
def backup_automatico():

    chave = request.args.get("key")

    if chave != os.getenv("BACKUP_KEY"):
        return "Acesso negado", 403

    criar_backup()

    return "Backup executado com sucesso"
def enviar_backup_drive(caminho_arquivo):

    token = json.loads(os.getenv("GOOGLE_TOKEN"))

    creds = Credentials.from_authorized_user_info(token)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    drive = build(
        "drive",
        "v3",
        credentials=creds
    )

    arquivo = {
        "name": os.path.basename(caminho_arquivo),
        "parents": [os.getenv("GOOGLE_DRIVE_FOLDER_ID")]
    }

    media = MediaFileUpload(
        caminho_arquivo,
        mimetype="application/json",
        resumable=True
    )

    drive.files().create(
        body=arquivo,
        media_body=media,
        fields="id"
    ).execute()

@app.route('/migrar')
def migrar():

    try:
        db.engine.execute(
            "ALTER TABLE usuario ADD COLUMN permissoes TEXT DEFAULT '[]'"
        )
        return "OK - coluna criada"

    except Exception as e:
        return str(e)
    
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run()
