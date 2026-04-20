from fastapi import APIRouter

router = APIRouter()


@router.get("")
def get_definicoes():
    return {
        "origens": ["COMPRA", "NASCIMENTO", "TROCA"],
        "racas": ["ANGUS", "BRAHMAN", "CHAROLÊS", "JERSEY", "NELORE", "GIROLANDO", "SIMENTAL"],
        "tipos": ["BEZERRO", "BEZERRA", "NOVILHA", "GARROTE", "BOI", "TOURO", "VACA"],
        "status_animal": ["ATIVO", "MORTO", "ABATIDO", "VENDIDO"],
        "causas_morte": ["ABORTO", "DOENÇA", "CAUSAS EXTERNAS"],
        "pastos": ["PASTO 1", "PASTO 2", "PASTO 3"],
        "classificacoes_sanidade": ["MEDICAMENTO", "VACINA", "VERMIFUGO"],
        "medicamentos": ["MEDICAMENTO A", "MEDICAMENTO B", "VACINA A", "VACINA B", "VERMIFUGO A"],
        "tipos_despesa": ["INSUMOS", "FUNCIONÁRIO", "TRANSPORTE", "INTERNET", "OUTROS"],
        "status_despesa": ["PAGO", "PENDENTE"],
        "status_inseminacao": ["CONFIRMADA", "NÃO CONFIRMADA", "AGUARDANDO"],
        "prenhez": ["SIM", "NÃO", "AGUARDANDO"],
        "ufs": [
            "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
            "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
            "RO", "RR", "RS", "SC", "SE", "SP", "TO",
        ],
    }
