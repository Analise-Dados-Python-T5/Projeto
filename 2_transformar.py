from datetime import datetime #converte texto de data para um objeto date

import pandas as pd

from banco import conectar, executar, inserir_em_lote
from config import TAMANHO_BLOCO

VALORES_VAZIOS = {"", "nan", "sem informação", "sem informacao", "none"}

def converter_valor(texto):
    if texto is None:
        return None #sem texto nenhum, não há o que converter
    texto = str(texto).strip() #garantir que é string e vou remover espacos no inicio/fim
    if texto.lower() in VALORES_VAZIOS:
        return None #texto so diz "vazio/sem informacao"
    texto = texto.replace(".", "").replace(",", ".") # remove os pontos de milhar e troca a vírgula decimal por ponto
    try:
        return float(texto) #converter o texto numerico para float
    except ValueError:
        return None


def converter_data(texto):
    if texto is None:
        return None #se não tenho nada, não preciso transformar nada 
    texto = str(texto).strip() 
    if texto.lower() in VALORES_VAZIOS:
        return None #converter todos os tipos de valores vazios em None
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date() #le "DD/MM/AAAA" e devolve so a data
    except ValueError:
        return None


def converter_inteiro(texto):
    valor = converter_valor(texto)
    return int(valor) if valor is not None else None #float -> int


def filtrar(df, mascara, tabela, motivo):
    antes = len(df) #tamanho antes
    df = df[mascara] #mascara e uma lista true/false, manter apenas as linhas com true
    descartadas = antes - len(df) #quantidade descartadas
    if descartadas:
        print(f"[transformar] {tabela}: {descartadas} linhas descartadas ({motivo}).")
    return df

#manter apenas 1 ocorrencia 
def remover_duplicadas(df, colunas_chave, tabela):
    antes = len(df) #tamanho antes
    df = df.drop_duplicates(subset=colunas_chave, keep="first") #so a 1° linha de cada chave repetida
    descartadas = antes - len(df) #quantidade descartados
    if descartadas:
        print(f"[transformar] {tabela}: {descartadas} linhas duplicadas descartadas.")
    return df


def inserir_em_blocos(conexao, sql, linhas, tamanho_bloco=TAMANHO_BLOCO):
    for inicio in range(0, len(linhas), tamanho_bloco):
        inserir_em_lote(conexao, sql, linhas[inicio:inicio + tamanho_bloco])


def inserir_no_silver(conexao, tabela, colunas, df):
    df_final = df[colunas] #mantem só as colunas que a tabela silver tem 
    df_final = df_final.where(pd.notnull(df_final), None)

    sql_insert = (
        f"INSERT INTO {tabela} ({', '.join(colunas)}) "
        f"VALUES ({', '.join(['%s'] * len(colunas))})"
    )
    linhas = [tuple(linha) for linha in df_final.itertuples(index=False, name=None)]
    inserir_em_blocos(conexao, sql_insert, linhas)
    print(f"[transformar] {tabela}: {len(linhas)} linhas carregadas.")


def transformar_viagem(conexao):
    df = pd.read_sql("SELECT * FROM raw_viagem;", conexao)

    df["id_viagem"] = df["id_viagem"].str.strip()
    df["nome_orgao_superior"] = df["nome_orgao_superior"].str.strip()

    df = filtrar(df, (df["id_viagem"] != "") & (df["nome_orgao_superior"] != ""),
                 "silver_viagem", "id_viagem ou nome_orgao_superior vazio")
    df = remover_duplicadas(df, "id_viagem", "silver_viagem")

    df["data_inicio"] = df["data_inicio"].map(converter_data) #aplica a conversao
    df["data_fim"] = df["data_fim"].map(converter_data)

    for coluna in ["valor_diarias", "valor_passagens", "valor_devolucao", "valor_outros_gastos"]:
        df[coluna] = df[coluna].map(converter_valor)

    valores_zerados = df[["valor_diarias", "valor_passagens",
                           "valor_devolucao", "valor_outros_gastos"]].fillna(0.0)
    df["valor_total"] = (
        valores_zerados["valor_diarias"]
        + valores_zerados["valor_passagens"]
        + valores_zerados["valor_outros_gastos"]
        - valores_zerados["valor_devolucao"]
    ).round(2)

    duracao = (df["data_fim"] - df["data_inicio"])
    df["duracao_dias"] = duracao.map(
        lambda d: (d.days + 1) if pd.notnull(d) else None
    )

    colunas = [
        "id_viagem", "num_proposta", "situacao", "viagem_urgente",
        "cod_orgao_superior", "nome_orgao_superior", "nome_viajante", "cargo",
        "data_inicio", "data_fim", "destinos", "motivo", "valor_diarias",
        "valor_passagens", "valor_devolucao", "valor_outros_gastos",
        "valor_total", "duracao_dias",
    ]
    inserir_no_silver(conexao, "silver_viagem", colunas, df)

    return set(df["id_viagem"])


def transformar_passagem(conexao, ids_validos):
    df = pd.read_sql("SELECT * FROM raw_passagem;", conexao)
    df["id_viagem"] = df["id_viagem"].str.strip()

    df = filtrar(df, df["id_viagem"].isin(ids_validos),
                 "silver_passagem", "id_viagem inexistente na silver_viagem")

    df["valor_passagem"] = df["valor_passagem"].map(converter_valor)
    df["taxa_servico"] = df["taxa_servico"].map(converter_valor)
    df["data_emissao"] = df["data_emissao"].map(converter_data)

    colunas = [
        "id_viagem", "meio_transporte", "pais_origem_ida", "uf_origem_ida",
        "cidade_origem_ida", "pais_destino_ida", "uf_destino_ida",
        "cidade_destino_ida", "valor_passagem", "taxa_servico", "data_emissao",
    ]
    inserir_no_silver(conexao, "silver_passagem", colunas, df)


def transformar_pagamento(conexao, ids_validos):
    df = pd.read_sql("SELECT * FROM raw_pagamento;", conexao)
    df["id_viagem"] = df["id_viagem"].str.strip()
    df["tipo_pagamento"] = df["tipo_pagamento"].str.strip()

    df = filtrar(df, df["id_viagem"].isin(ids_validos) & (df["tipo_pagamento"] != ""),
                 "silver_pagamento", "id_viagem invalido ou tipo_pagamento vazio")

    df["valor"] = df["valor"].map(converter_valor)

    colunas = [
        "id_viagem", "num_proposta", "nome_orgao_pagador", "nome_ug_pagadora",
        "tipo_pagamento", "valor",
    ]
    inserir_no_silver(conexao, "silver_pagamento", colunas, df)


def transformar_trecho(conexao, ids_validos):
    df = pd.read_sql("SELECT * FROM raw_trecho;", conexao)
    df["id_viagem"] = df["id_viagem"].str.strip()
    df["sequencia_trecho"] = df["sequencia_trecho"].map(converter_inteiro)

    df = filtrar(df, df["id_viagem"].isin(ids_validos) & df["sequencia_trecho"].notnull(),
                 "silver_trecho", "id_viagem invalido ou sequencia ausente")
    df = remover_duplicadas(df, ["id_viagem", "sequencia_trecho"], "silver_trecho")

    df["origem_data"] = df["origem_data"].map(converter_data)
    df["destino_data"] = df["destino_data"].map(converter_data)
    df["numero_diarias"] = df["numero_diarias"].map(converter_valor)

    colunas = [
        "id_viagem", "sequencia_trecho", "origem_data", "origem_uf",
        "origem_cidade", "destino_data", "destino_uf", "destino_cidade",
        "meio_transporte", "numero_diarias",
    ]
    inserir_no_silver(conexao, "silver_trecho", colunas, df)


def main():
    conexao = conectar()
    try:
        executar(
            conexao,
            "TRUNCATE TABLE silver_viagem, silver_pagamento, silver_passagem, "
            "silver_trecho RESTART IDENTITY CASCADE;",
        )

        ids_validos = transformar_viagem(conexao)

        for nome, funcao in (
            ("silver_passagem", transformar_passagem),
            ("silver_pagamento", transformar_pagamento),
            ("silver_trecho", transformar_trecho),
        ):
            try:
                funcao(conexao, ids_validos)
            except Exception as erro:
                print(f"[transformar] ERRO ao processar '{nome}': {erro}")
    finally:
        conexao.close()


if __name__ == "__main__":
    main()
