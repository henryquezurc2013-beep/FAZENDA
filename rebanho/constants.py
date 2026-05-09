"""Constantes compartilhadas entre routers."""

# Estimativa de idade na compra: 8 meses → data_nascimento = data_compra - 240 dias.
# Usado em /animais/importar (CSV) e /balanca/importar (auto-cadastro).
DATA_NASCIMENTO_OFFSET_DIAS = 240
