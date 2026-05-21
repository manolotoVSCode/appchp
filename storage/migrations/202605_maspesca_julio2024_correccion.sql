-- Corrección: factura CFE julio 2024 de MASPESCA (cliente_id=42, contrato_id=10)
-- Capturada manualmente en v2.37.0 sin campos de consumo ni MEM.
-- Ejecutar manualmente en la consola de Supabase SQL Editor.
-- Idempotente: usa UPDATE y DELETE+INSERT con WHERE específico.
-- Versión: v2.38.2 / 2026-05-21

DO $$
DECLARE
  v_factura_id  INT;

  -- Consumos por horario (kWh)
  v_kwh_base    NUMERIC := 11530;
  v_kwh_inter   NUMERIC := 25106;
  v_kwh_punta   NUMERIC := 2281;
  v_kwh_total   NUMERIC;

  -- Componentes MEM relevantes para costo unitario (MXN)
  v_gen_b       NUMERIC := 12846.73;
  v_gen_i       NUMERIC := 50668.93;
  v_gen_p       NUMERIC :=  5191.78;
  v_transmision NUMERIC :=  6884.42;
  v_cenace      NUMERIC :=   252.97;
  v_scnmem      NUMERIC :=   241.29;

  -- Costo unitario derivado (MXN/kWh)
  -- Fórmula: shared = (transmision + cenace + scnmem) / kwh_total
  --          costo_h = gen_h / kwh_h + shared
  v_shared      NUMERIC;
  v_cu_base     NUMERIC;
  v_cu_inter    NUMERIC;
  v_cu_punta    NUMERIC;
BEGIN
  -- Calcular costo_unitario_kwh (campo derivado, no viene del PDF)
  v_kwh_total := v_kwh_base + v_kwh_inter + v_kwh_punta;
  v_shared    := (v_transmision + v_cenace + v_scnmem) / v_kwh_total;
  v_cu_base   := ROUND(v_gen_b / v_kwh_base  + v_shared, 6);
  v_cu_inter  := ROUND(v_gen_i / v_kwh_inter + v_shared, 6);
  v_cu_punta  := ROUND(v_gen_p / v_kwh_punta + v_shared, 6);

  -- Obtener el ID de la factura de julio 2024 del cliente MASPESCA
  SELECT id INTO v_factura_id
  FROM cfe_facturas
  WHERE cliente_id = 42
    AND contrato_id = 10
    AND validacion_manual = TRUE
    AND anio = 2024
    AND mes = 7
  LIMIT 1;

  IF v_factura_id IS NULL THEN
    RAISE EXCEPTION 'Factura no encontrada: cliente_id=42, contrato_id=10, anio=2024, mes=7. Verificar IDs.';
  END IF;

  -- Actualizar campos de la fila principal en cfe_facturas
  UPDATE cfe_facturas SET
    periodo_inicio             = '2024-06-30',
    periodo_fin                = '2024-07-31',
    fecha_emision              = '2024-08-03',
    fecha_limite_pago          = '2024-08-12',
    folio                      = '000061221132',
    kw_max                     = '99',
    kvarh                      = '17509',
    factor_potencia_pct        = '91.20',
    cargo_fijo_mxn             = '441.87',
    energia_total_mxn          = '118888.22',
    cargo_factor_potencia_mxn  = '-357.99',
    subtotal_mxn               = '118972.10',
    iva_mxn                    = '19035.54',
    facturacion_periodo_mxn    = '138007.64',
    derecho_alumbrado_publico_mxn = '59.40',
    credito_aplicado_mxn       = '-94521.00',
    total_mxn                  = '138067.22'
  WHERE id = v_factura_id;

  -- Reinsertar periodos con costo_unitario_kwh calculado
  DELETE FROM cfe_periodos WHERE factura_id = v_factura_id;
  INSERT INTO cfe_periodos (factura_id, periodo, consumo_kwh, demanda_kw, costo_unitario_kwh)
  VALUES
    (v_factura_id, 'base',       v_kwh_base::TEXT,  '68', v_cu_base::TEXT),
    (v_factura_id, 'intermedio', v_kwh_inter::TEXT, '99', v_cu_inter::TEXT),
    (v_factura_id, 'punta',      v_kwh_punta::TEXT, '81', v_cu_punta::TEXT);

  -- Reinsertar componentes MEM con asignación correcta de tipo de cargo
  -- Suministro             → cargo_fijo_mxn
  -- Distribución, Capacidad → cargo_demanda_mxn
  -- Transmisión, CENACE, Generación B/I/P, SCnMEM → cargo_energia_mxn
  DELETE FROM cfe_mem_componentes WHERE factura_id = v_factura_id;
  INSERT INTO cfe_mem_componentes (factura_id, nombre, cargo_fijo_mxn, cargo_demanda_mxn, cargo_energia_mxn, importe_mxn)
  VALUES
    (v_factura_id, 'Suministro',    '441.87',  '0',         '0',         '441.87'),
    (v_factura_id, 'Distribución',  '0',       '8780.48',   '0',         '8780.48'),
    (v_factura_id, 'Transmisión',   '0',       '0',         '6884.42',   '6884.42'),
    (v_factura_id, 'CENACE',        '0',       '0',          '252.97',    '252.97'),
    (v_factura_id, 'Generación B',  '0',       '0',        '12846.73',  '12846.73'),
    (v_factura_id, 'Generación I',  '0',       '0',        '50668.93',  '50668.93'),
    (v_factura_id, 'Generación P',  '0',       '0',         '5191.78',   '5191.78'),
    (v_factura_id, 'Capacidad',     '0',      '34021.62',    '0',        '34021.62'),
    (v_factura_id, 'SCnMEM',        '0',       '0',          '241.29',    '241.29');

  RAISE NOTICE 'OK: factura id=% (MASPESCA julio 2024) corregida. cu_base=%, cu_inter=%, cu_punta=%',
    v_factura_id, v_cu_base, v_cu_inter, v_cu_punta;
END;
$$;
