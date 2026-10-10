import zipfile #le arquivos de dentro de um .zip sem extrair

import gdown #baixa arquivos grandes do Google Drive
import pandas as pd 

from banco import conectar, executar, inserir_em_lote #funcoes prontas de acesso ao banco
from config import ( # parametros do projeto
    ARQUIVOS, #mapa csv
    CSV_ENCODING, # acentuacao no padrao ISO-8859-1
    CSV_SEPARADOR, #;
    DRIVE_FILE_ID, #id do aruqivo .zip no google drive
    PASTA_DADOS, #pasta local onde .zip vai ficar guardado
    TAMANHO_BLOCO, #quntas linhas ler/inserir por vez
)

NOME_ZIP = "viagens_2025_6meses.zip" #nome do arquivo depois de baixado
CAMINHO_ZIP = PASTA_DADOS / NOME_ZIP #caminho completo


#Ordem exata das colunas de cada CSV
COLUNAS_RAW = {
    "viagem": [
        "id_viagem", "num_proposta", "situacao", "viagem_urgente",
        "justificativa_urgencia", "cod_orgao_superior", "nome_orgao_superior",
        "cod_orgao_solicitante", "nome_orgao_solicitante", "cpf_viajante",
        "nome_viajante", "cargo", "funcao", "descricao_funcao", "data_inicio",
        "data_fim", "destinos", "motivo", "valor_diarias", "valor_passagens",
        "valor_devolucao", "valor_outros_gastos",
    ],
    "pagamento": [
        "id_viagem", "num_proposta", "cod_orgao_superior", "nome_orgao_superior",
        "cod_orgao_pagador", "nome_orgao_pagador", "cod_ug_pagadora",
        "nome_ug_pagadora", "tipo_pagamento", "valor",
    ],
    "passagem": [
        "id_viagem", "num_proposta", "meio_transporte", "pais_origem_ida",
        "uf_origem_ida", "cidade_origem_ida", "pais_destino_ida",
        "uf_destino_ida", "cidade_destino_ida", "pais_origem_volta",
        "uf_origem_volta", "cidade_origem_volta", "pais_destino_volta",
        "uf_destino_volta", "cidade_destino_volta", "valor_passagem",
        "taxa_servico", "data_emissao", "hora_emissao",
    ],
    "trecho": [
        "id_viagem", "num_proposta", "sequencia_trecho", "origem_data",
        "origem_pais", "origem_uf", "origem_cidade", "destino_data",
        "destino_pais", "destino_uf", "destino_cidade", "meio_transporte",
        "numero_diarias", "missao",
    ],
}


def baixar_arquivo_drive(file_id, destino):
    destino.parent.mkdir(parents=True, exist_ok=True) #cria a pasta "data" se não existir
    gdown.download(id=file_id, output=str(destino), quiet=False) #baixa e salva no destino

def garantir_arquivo_zip():
    if CAMINHO_ZIP.exists():
        print(f"[extrair] usando arquivo ja existente: {CAMINHO_ZIP}")
        return

    if not DRIVE_FILE_ID or DRIVE_FILE_ID.startswith("COLE_AQUI"):
        raise RuntimeError(
            "Arquivo de dados nao encontrado em "
            f"'{CAMINHO_ZIP}' e DRIVE_FILE_ID nao foi configurado no config.py."
        )

    print("[extrair] baixando .zip do Google Drive...")
    baixar_arquivo_drive(DRIVE_FILE_ID, CAMINHO_ZIP)
    print(f"[extrair] download concluido: {CAMINHO_ZIP}")


def carregar_csv_na_raw(conexao, arquivo_zip, chave, info):
    colunas = COLUNAS_RAW[chave] #lista de nomes de coluna dessa tabela 
    tabela = info["tabela_raw"] #nome da tabela raw_* no banco

    executar(conexao, f"TRUNCATE TABLE {tabela};") #TRUNCATE para não duplicar os dados

    placeholders = ", ".join(["%s"] * len(colunas)) #ex. '(%s, %s, %s)'
    sql_insert = f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({placeholders})"

    total_linhas = 0 #conta quantas linhas essa tabela recebeu
    with arquivo_zip.open(info["csv"]) as csv_bruto:
        leitor = pd.read_csv(
            csv_bruto,
            sep=CSV_SEPARADOR,
            encoding=CSV_ENCODING,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            chunksize=TAMANHO_BLOCO,
        )
        for bloco in leitor:
            bloco.columns = colunas
            linhas = [tuple(linha) for linha in bloco.itertuples(index=False, name=None)]
            inserir_em_lote(conexao, sql_insert, linhas)
            total_linhas += len(linhas)

    print(f"[extrair] {tabela}: {total_linhas} linhas carregadas.")


def main():
    garantir_arquivo_zip() #baixa .zip se ainda não estiver na pasta data
    conexao = conectar() #abre a conexao com o PostgreSQL 

    try:
        with zipfile.ZipFile(CAMINHO_ZIP) as arquivo_zip:
            for chave, info in ARQUIVOS.items(): #percorre viagem, pagamento, passagem, trecho
                try:
                    carregar_csv_na_raw(conexao, arquivo_zip, chave, info)
                except Exception as erro:
                    print(f"[extrair] ERRO ao processar '{chave}': {erro}")
    finally:
        conexao.close()


if __name__ == "__main__":
    main()
