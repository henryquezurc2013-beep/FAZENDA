import json as _json
from datetime import date, timedelta
from database import SessionLocal, create_tables
from models import (
    Animal, Pesagem, Sanidade, Inseminacao, Compra, Venda, Despesa, Pessoa,
    Pasto, Piquete, MedicaoPasto, LotePasto, ManejoPastagem, AdubacaoPastagem, Chuva,
    Lote, LoteAnimal, Config,
)

today = date.today()


def fmt(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _existe(db, model, **kwargs):
    return db.query(model).filter_by(**kwargs).first() is not None


def _atualizar_custos_animal(animal: Animal, valor_compra: float | None = None):
    if valor_compra is not None:
        animal.valor_compra = valor_compra
    if animal.valor_compra and animal.peso_atual and animal.peso_atual > 0:
        animal.custo_kg = round(animal.valor_compra / animal.peso_atual, 2)
        animal.custo_arroba = round(animal.valor_compra / (animal.peso_atual / 15), 2)
    else:
        animal.custo_kg = None
        animal.custo_arroba = None


def run():
    create_tables()
    db = SessionLocal()

    try:
        # ── Animais ──────────────────────────────────────────────────
        if not _existe(db, Animal, brinco="BOI-001"):
            db.add(Animal(
                brinco="BOI-001", tipo="BOI", status="ATIVO", pasto="PASTO 1",
                peso_atual=465.0, raca="NELORE", sexo="MACHO", origem="NASCIMENTO",
                data_nascimento="2022-01-15", valor_compra=2500.0,
            ))
        if not _existe(db, Animal, brinco="BEZ-003"):
            db.add(Animal(
                brinco="BEZ-003", tipo="BEZERRO", status="ATIVO", pasto="PASTO 1",
                raca="NELORE", sexo="MACHO", origem="NASCIMENTO",
                data_nascimento=fmt(today - timedelta(days=180)),
            ))
        if not _existe(db, Animal, brinco="VAC-001"):
            db.add(Animal(
                brinco="VAC-001", tipo="VACA", status="MORTO", pasto="PASTO 2",
                raca="ANGUS", sexo="FÊMEA", origem="COMPRA",
                data_nascimento="2019-03-10",
                data_morte="2024-01-10", motivo_morte="DOENÇA",
                mes_morte=1, ano_morte=2024, valor_compra=3200.0,
            ))
        if not _existe(db, Animal, brinco="VAC-002"):
            db.add(Animal(
                brinco="VAC-002", tipo="VACA", status="ATIVO", pasto="PASTO 1",
                peso_atual=382.0, raca="NELORE", sexo="FÊMEA", origem="COMPRA",
                data_nascimento="2020-06-20", valor_compra=2800.0,
                custo_kg=round(2800/382, 2), custo_arroba=round(2800/(382/15), 2),
            ))

        db.flush()

        for brinco, valor in (("BOI-001", 2500.0), ("VAC-001", 3200.0), ("VAC-002", 2800.0)):
            animal = db.query(Animal).filter_by(brinco=brinco).first()
            if animal:
                _atualizar_custos_animal(animal, valor)

        # ── Pesagem ───────────────────────────────────────────────────
        # BOI-001: 3 pesagens para GMD calculável (prompt previsao-saida)
        d_pes1 = today - timedelta(days=60)
        if not _existe(db, Pesagem, brinco="BOI-001", data_pesagem=fmt(d_pes1)):
            db.add(Pesagem(brinco="BOI-001", data_pesagem=fmt(d_pes1),
                peso=420.0, ganho_kg=20.0, mes=d_pes1.month, ano=d_pes1.year, pasto="PASTO 1"))
        d_pes2 = today - timedelta(days=30)
        if not _existe(db, Pesagem, brinco="BOI-001", data_pesagem=fmt(d_pes2)):
            db.add(Pesagem(brinco="BOI-001", data_pesagem=fmt(d_pes2),
                peso=445.0, ganho_kg=25.0, mes=d_pes2.month, ano=d_pes2.year, pasto="PASTO 1"))
        if not _existe(db, Pesagem, brinco="BOI-001", data_pesagem=fmt(today)):
            db.add(Pesagem(brinco="BOI-001", data_pesagem=fmt(today),
                peso=465.0, ganho_kg=20.0, mes=today.month, ano=today.year, pasto="PASTO 1"))
        # VAC-002: 2 pesagens
        d_vac1 = today - timedelta(days=45)
        if not _existe(db, Pesagem, brinco="VAC-002", data_pesagem=fmt(d_vac1)):
            db.add(Pesagem(brinco="VAC-002", data_pesagem=fmt(d_vac1),
                peso=360.0, ganho_kg=0.0, mes=d_vac1.month, ano=d_vac1.year, pasto="PASTO 1"))
        if not _existe(db, Pesagem, brinco="VAC-002", data_pesagem=fmt(today)):
            db.add(Pesagem(brinco="VAC-002", data_pesagem=fmt(today),
                peso=382.0, ganho_kg=22.0, mes=today.month, ano=today.year, pasto="PASTO 1"))

        # ── Sanidade ──────────────────────────────────────────────────
        d_san = today - timedelta(days=15)
        if not _existe(db, Sanidade, brinco="BOI-001", data=fmt(d_san), medicamento="VACINA A"):
            db.add(Sanidade(
                brinco="BOI-001", data=fmt(d_san),
                medicamento="VACINA A", classificacao="VACINA", status="ATIVO",
            ))

        # ── Inseminação ───────────────────────────────────────────────
        d_ins = today - timedelta(days=60)
        if not _existe(db, Inseminacao, brinco="VAC-002", data_insem=fmt(d_ins)):
            db.add(Inseminacao(
                brinco="VAC-002", data_insem=fmt(d_ins),
                prenhez="SIM", status="CONFIRMADA",
            ))

        # ── Compra ────────────────────────────────────────────────────
        d_cmp = today - timedelta(days=90)
        if not _existe(db, Compra, fornecedor="Agropecuária Brasil", data=fmt(d_cmp)):
            db.add(Compra(
                fornecedor="Agropecuária Brasil", descricao="Compra de insumos",
                data=fmt(d_cmp), valor_unit=4000.0, quantidade=1,
                valor_total=4000.0, mes=d_cmp.month, ano=d_cmp.year,
            ))

        # ── Venda ─────────────────────────────────────────────────────
        d_vnd = today - timedelta(days=45)
        if not _existe(db, Venda, cliente="João da Silva", data=fmt(d_vnd)):
            db.add(Venda(
                cliente="João da Silva", descricao="Venda de animal",
                data=fmt(d_vnd), valor_unit=3500.0, quantidade=1,
                valor_total=3500.0, mes=d_vnd.month, ano=d_vnd.year,
            ))

        # ── Despesas ──────────────────────────────────────────────────
        d_dp1 = today - timedelta(days=10)
        if not _existe(db, Despesa, tipo="INSUMOS", vencimento=fmt(d_dp1)):
            db.add(Despesa(
                tipo="INSUMOS", descricao="Compra de sal mineral",
                valor=250.0, vencimento=fmt(d_dp1),
                status="PAGO", mes=d_dp1.month, ano=d_dp1.year,
            ))
        if not _existe(db, Despesa, tipo="FUNCIONÁRIO", vencimento=fmt(today)):
            db.add(Despesa(
                tipo="FUNCIONÁRIO", descricao="Salário mensal",
                valor=1800.0, vencimento=fmt(today),
                status="PENDENTE", mes=today.month, ano=today.year,
            ))

        # ── Pessoas ───────────────────────────────────────────────────
        if not _existe(db, Pessoa, codigo="CLI-001"):
            db.add(Pessoa(
                tipo="CLIENTE", pessoa="Pessoa Física", codigo="CLI-001",
                nome="João da Silva", uf="GO",
            ))
        if not _existe(db, Pessoa, codigo="FOR-001"):
            db.add(Pessoa(
                tipo="FORNECEDOR", pessoa="Pessoa Jurídica", codigo="FOR-001",
                nome="Agropecuária Brasil", uf="GO",
            ))

        # ── Pastagem ──────────────────────────────────────────────────
        if not _existe(db, Pasto, nome="Área Norte"):
            db.add(Pasto(nome="Área Norte", area_ha=50, tipo_capim="Mombaça", sistema="ROTACIONADO"))
        db.flush()

        pasto = db.query(Pasto).filter_by(nome="Área Norte").first()

        _piquetes_seed = [
            ("P-01", 8, True,  False, False),
            ("P-02", 8, False, False, False),
            ("P-03", 8, False, True,  False),
            ("P-04", 8, False, False, True),
        ]
        for nome_pq, area, beb, coch, somb in _piquetes_seed:
            if not _existe(db, Piquete, nome=nome_pq, pasto_id=pasto.id):
                db.add(Piquete(
                    pasto_id=pasto.id, nome=nome_pq, area_ha=area,
                    tipo_capim="Mombaça",
                    altura_entrada_cm=35, altura_saida_cm=15, dias_descanso_alvo=28,
                    tem_bebedouro=beb, tem_cocho=coch, tem_sombra=somb,
                    status="DISPONIVEL",
                ))
        db.flush()

        p01 = db.query(Piquete).filter_by(nome="P-01", pasto_id=pasto.id).first()
        p02 = db.query(Piquete).filter_by(nome="P-02", pasto_id=pasto.id).first()
        p03 = db.query(Piquete).filter_by(nome="P-03", pasto_id=pasto.id).first()

        # Medições de hoje
        if not _existe(db, MedicaoPasto, piquete_id=p01.id, data=fmt(today)):
            db.add(MedicaoPasto(piquete_id=p01.id, data=fmt(today), altura_cm=38, cobertura_pct=95))
        if not _existe(db, MedicaoPasto, piquete_id=p02.id, data=fmt(today)):
            db.add(MedicaoPasto(piquete_id=p02.id, data=fmt(today), altura_cm=20, cobertura_pct=70))
        d_med_p03 = fmt(today - timedelta(days=5))
        if not _existe(db, MedicaoPasto, piquete_id=p03.id, data=d_med_p03):
            db.add(MedicaoPasto(piquete_id=p03.id, data=d_med_p03, altura_cm=28, cobertura_pct=85))
        # P-04: sem medição → SEM_DADOS
        db.flush()

        # Lote A no P-03 há 5 dias
        d_entrada_p03 = fmt(today - timedelta(days=5))
        if not _existe(db, ManejoPastagem, piquete_id=p03.id, lote="Lote A", data_entrada=d_entrada_p03):
            db.add(ManejoPastagem(
                piquete_id=p03.id, lote="Lote A", qtd_animais=20,
                peso_medio_kg=380, ua_total=round(380/450*20, 1),
                data_entrada=d_entrada_p03, altura_entrada=35,
            ))
            if not _existe(db, LotePasto, piquete_id=p03.id, lote="Lote A", status="ATIVO"):
                db.add(LotePasto(
                    data=d_entrada_p03, lote="Lote A", piquete_id=p03.id,
                    qtd_cabecas=20, peso_medio_kg=380, categoria="VACAS",
                    data_entrada=d_entrada_p03,
                    previsao_saida=fmt(today - timedelta(days=5) + timedelta(days=28)),
                    status="ATIVO",
                ))
            if p03:
                p03.status = "OCUPADO"
        db.flush()

        # P-02: descanso finalizado há 30 dias (para semáforo responder corretamente)
        d_saida_p02 = fmt(today - timedelta(days=30))
        if not _existe(db, ManejoPastagem, piquete_id=p02.id, data_saida=d_saida_p02):
            db.add(ManejoPastagem(
                piquete_id=p02.id, lote="Lote Y", qtd_animais=10,
                peso_medio_kg=350, ua_total=round(350/450*10, 1),
                data_entrada=fmt(today - timedelta(days=58)),
                data_saida=d_saida_p02, altura_entrada=36, altura_saida=14,
                dias_ocupacao=28, ganho_total_kg=60, ganho_ha_kg=7.5,
                condicao_pasto="REGULAR",
            ))

        # Coordenadas de exemplo (polígonos fictícios — usuário ajustará via modo edição)
        _coords_seed = {
            "P-01": [[-15.7080,-47.9230],[-15.7080,-47.9200],[-15.7105,-47.9200],[-15.7105,-47.9230]],
            "P-02": [[-15.7110,-47.9230],[-15.7110,-47.9200],[-15.7135,-47.9200],[-15.7135,-47.9230]],
            "P-03": [[-15.7080,-47.9195],[-15.7080,-47.9165],[-15.7105,-47.9165],[-15.7105,-47.9195]],
            "P-04": [[-15.7110,-47.9195],[-15.7110,-47.9165],[-15.7135,-47.9165],[-15.7135,-47.9195]],
        }
        for _nome_pq, _coords in _coords_seed.items():
            _pq_c = db.query(Piquete).filter_by(nome=_nome_pq, pasto_id=pasto.id).first()
            if _pq_c and not _pq_c.coordenadas:
                _pq_c.coordenadas = _json.dumps(_coords)

        # P-01: descanso finalizado há 30 dias (para semáforo VERDE)
        d_saida_p01 = fmt(today - timedelta(days=30))
        if not _existe(db, ManejoPastagem, piquete_id=p01.id, data_saida=d_saida_p01):
            db.add(ManejoPastagem(
                piquete_id=p01.id, lote="Lote X", qtd_animais=15,
                peso_medio_kg=400, ua_total=round(400/450*15, 1),
                data_entrada=fmt(today - timedelta(days=58)),
                data_saida=d_saida_p01, altura_entrada=36, altura_saida=16,
                dias_ocupacao=28, ganho_total_kg=120, ganho_ha_kg=15.0,
                condicao_pasto="BOA",
            ))
            if p01:
                p01.status = "EM_DESCANSO"

        # Adubação P-01 mês passado
        d_adub = fmt(today - timedelta(days=35))
        if not _existe(db, AdubacaoPastagem, piquete_id=p01.id, data=d_adub):
            db.add(AdubacaoPastagem(
                piquete_id=p01.id, data=d_adub, produto="Ureia",
                dose_kg_ha=80, custo_total=320.0, responsavel="João",
            ))

        # Chuva — últimos 3 meses (inclui mês seco para acionar alerta)
        chuvas_seed = []
        # Mês -2: 90mm (normal)
        for dia in [5, 12, 18, 25]:
            d = fmt(today - timedelta(days=60+dia))
            chuvas_seed.append((d, 22.5))
        # Mês -1: 30mm (seco — aciona alerta)
        for dia in [3, 20]:
            d = fmt(today - timedelta(days=30+dia))
            chuvas_seed.append((d, 15.0))
        # Mês atual: 45mm (abaixo de 50 → alerta de seca)
        for dia in [2, 8, 14]:
            d = fmt(today - timedelta(days=dia))
            chuvas_seed.append((d, 15.0))

        for data_c, mm in chuvas_seed:
            if not _existe(db, Chuva, data=data_c, mm_chuva=mm):
                db.add(Chuva(data=data_c, area="Fazenda Geral", mm_chuva=mm))

        # ── Lotes ─────────────────────────────────────────────────────
        p03_id = p03.id if p03 else None

        if not _existe(db, Lote, nome="Vacas Pasto Norte"):
            db.add(Lote(
                nome="Vacas Pasto Norte", categoria="VACAS",
                descricao="Vacas em lactação no pasto norte",
                piquete_id=p03_id, status="ATIVO",
                ua_total=round(380/450*20, 2),
            ))
        if not _existe(db, Lote, nome="Garrotes Engorda"):
            db.add(Lote(
                nome="Garrotes Engorda", categoria="GARROTES",
                descricao="Garrotes em fase de terminação",
                piquete_id=None, status="ATIVO",
                ua_total=round(450/450*1, 2),
            ))
        db.flush()

        lote_vacas = db.query(Lote).filter_by(nome="Vacas Pasto Norte").first()
        lote_garrotes = db.query(Lote).filter_by(nome="Garrotes Engorda").first()

        if lote_vacas and not _existe(db, LoteAnimal, lote_id=lote_vacas.id, brinco="VAC-002"):
            db.add(LoteAnimal(
                lote_id=lote_vacas.id, brinco="VAC-002",
                data_entrada=fmt(today - timedelta(days=5)), status="ATIVO",
            ))
        if lote_garrotes and not _existe(db, LoteAnimal, lote_id=lote_garrotes.id, brinco="BOI-001"):
            db.add(LoteAnimal(
                lote_id=lote_garrotes.id, brinco="BOI-001",
                data_entrada=fmt(today - timedelta(days=30)), status="ATIVO",
            ))

        # ── Config ────────────────────────────────────────────────────
        for chave, valor in (("peso_alvo_padrao", "480"), ("preco_arroba_padrao", "320")):
            if not _existe(db, Config, chave=chave):
                db.add(Config(chave=chave, valor=valor))

        db.commit()
        print("Seed concluído com sucesso! Banco rebanho.db criado/atualizado.")

    except Exception as e:
        db.rollback()
        print(f"Erro ao executar seed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
