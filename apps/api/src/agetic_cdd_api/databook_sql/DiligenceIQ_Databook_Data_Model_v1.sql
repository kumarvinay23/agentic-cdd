-- =====================================================================================================
-- DiligenceIQ databook DATA MODEL  (PostgreSQL 16)                          ontology version 1.0.0
-- =====================================================================================================
-- What this file is
--   The database that holds every deal's databook. One row in FACT = one number, tied to an ontology
--   item (concept) and to the source cell it was read from. The ontology itself is loaded into the
--   ONTO_* tables, so the database refuses any fact whose concept, reason code or document type is not
--   in the ontology.
-- How to run
--   1. psql -d <db> -f databook_postgres.sql      (this file: creates the tables; run once per database)
--   2. psql -d <db> -f ontology_seed.sql          (loads ontology version 1.0.0; run again for each new version)
-- Part A  ontology reference tables (onto_*): the same for every deal, versioned, read-only for the pipeline
-- Part B  deal data tables: deal, document, source_location, dimension_member, fact, record,
--         reconciliation, flag, mapping_decision
-- Part C  views the databook publisher and reviewers use
-- Nothing here names a company, file or sheet. Deal data lives only in Part B rows.
-- =====================================================================================================

-- ------------------------------------------------------------------------ PART A: ontology reference
CREATE TABLE onto_version (
  version        text PRIMARY KEY,
  released       date,
  loaded_at      timestamptz NOT NULL DEFAULT now(),
  bundle         jsonb NOT NULL                      -- the whole ontology file, kept for audit
);
COMMENT ON TABLE onto_version IS 'One row per ontology release. Every deal and every fact records the version it was built with.';

CREATE TABLE onto_concept (
  version             text NOT NULL REFERENCES onto_version,
  concept_id          text NOT NULL,                 -- e.g. fin.pl.revenue
  label               text NOT NULL,
  concept_class       text NOT NULL,                 -- line, subtotal, derived, kpi, ...
  statement           text NOT NULL,                 -- PL, BS, CF, DERIVED, KPI, ...
  parent_id           text,                          -- where it rolls up
  weight              numeric NOT NULL DEFAULT 1,    -- sign in the roll-up (-1 for outflows)
  signed              boolean NOT NULL DEFAULT false,-- false = stored as a positive magnitude
  period_nature       text,                          -- duration, instant, none
  unit_type           text,
  aggregation         text,                          -- sum, first, last, formula, none
  split_dimension     text,                          -- the dimension that holds its splits
  dimensions_allowed  text[] NOT NULL DEFAULT '{}',
  dimensions_required text[] NOT NULL DEFAULT '{}',
  synonyms            text[] NOT NULL DEFAULT '{}',
  schedules           text[] NOT NULL DEFAULT '{}', -- databook tabs that use it
  evidence_doc_types  text[] NOT NULL DEFAULT '{}', -- documents allowed to evidence it
  sector_pack         text,
  definition          text,
  PRIMARY KEY (version, concept_id),
  FOREIGN KEY (version, parent_id) REFERENCES onto_concept (version, concept_id) DEFERRABLE INITIALLY DEFERRED
);
COMMENT ON TABLE onto_concept IS 'Every item a databook can contain (283 in v1.0.0). A fact must point to one of these.';

CREATE TABLE onto_dimension (version text NOT NULL REFERENCES onto_version, dimension_id text NOT NULL, kind text NOT NULL,
  members text[] NOT NULL DEFAULT '{}', note text, PRIMARY KEY (version, dimension_id));
COMMENT ON TABLE onto_dimension IS 'Ways a concept can be split (service_line, view, facility ...). Closed dimensions list their members.';

CREATE TABLE onto_document_type (version text NOT NULL REFERENCES onto_version, doc_type text NOT NULL, label text NOT NULL,
  evidence_tier char(1) NOT NULL, default_basis text, modules text[] NOT NULL DEFAULT '{}', recognition_hints text[] NOT NULL DEFAULT '{}',
  PRIMARY KEY (version, doc_type));
COMMENT ON TABLE onto_document_type IS 'Classes of data-room document, with evidence tier A/B/C.';

CREATE TABLE onto_authority (version text NOT NULL REFERENCES onto_version, fact_family text NOT NULL, rank int NOT NULL, doc_type text NOT NULL,
  PRIMARY KEY (version, fact_family, rank), FOREIGN KEY (version, doc_type) REFERENCES onto_document_type);
COMMENT ON TABLE onto_authority IS 'Which document wins when two disagree: rank 1 is the highest authority within a fact family.';

CREATE TABLE onto_schedule (version text NOT NULL REFERENCES onto_version, schedule_id text NOT NULL, name text NOT NULL, report text NOT NULL,
  completeness_weight int NOT NULL, required_periods text[] NOT NULL, required_concepts text[] NOT NULL, record_classes text[] NOT NULL, purpose text,
  PRIMARY KEY (version, schedule_id));
COMMENT ON TABLE onto_schedule IS 'The databook tabs (FDD-01..19, CDD-01..14, GOV-01..05) and what each must contain.';

CREATE TABLE onto_calculation (version text NOT NULL REFERENCES onto_version, calc_id text NOT NULL, seq int NOT NULL, target text NOT NULL,
  expression text NOT NULL, period_types text[] NOT NULL, note text, PRIMARY KEY (version, calc_id));
COMMENT ON TABLE onto_calculation IS 'How the engine derives totals and ratios from stored lines, run in seq order.';

CREATE TABLE onto_rule (version text NOT NULL REFERENCES onto_version, rule_id text NOT NULL, rule_type text NOT NULL, severity text NOT NULL,
  description text NOT NULL, definition jsonb NOT NULL, PRIMARY KEY (version, rule_id));
COMMENT ON TABLE onto_rule IS 'Validation rules. severity block = stops the tab publishing; warn = shown beside the figure; flag = review list.';

CREATE TABLE onto_reason_code (version text NOT NULL REFERENCES onto_version, code text NOT NULL, meaning text NOT NULL, PRIMARY KEY (version, code));
COMMENT ON TABLE onto_reason_code IS 'Why a fact is HELD, REJECTED or COMPARATIVE.';

CREATE TABLE onto_record_class (version text NOT NULL REFERENCES onto_version, record_class text NOT NULL, fields text[] NOT NULL,
  PRIMARY KEY (version, record_class));
COMMENT ON TABLE onto_record_class IS 'Multi-field items that are not single numbers: facility, lease, adjustment, competitor, finding ...';

-- ------------------------------------------------------------------------ PART B: deal data
CREATE TABLE deal (
  deal_id             text PRIMARY KEY,
  deal_name           text,
  target_entity       text,
  ontology_version    text NOT NULL REFERENCES onto_version,
  reporting_currency  char(3) NOT NULL,
  fiscal_year_end     char(5) NOT NULL CHECK (fiscal_year_end ~ '^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$'),   -- MM-DD
  latest_actual_month date NOT NULL,                 -- drives YTD, LTM and which facts count as actual
  history_years       int NOT NULL DEFAULT 3,
  sector_packs        text[] NOT NULL DEFAULT '{}',
  ebitda_policy       jsonb NOT NULL DEFAULT '{}',  -- e.g. include_other_operating_income
  materiality         numeric,
  confirmed_by        text,                          -- nothing publishes until a person confirms the profile
  confirmed_at        timestamptz
);
COMMENT ON TABLE deal IS 'One deal and the settings a person confirms before the databook is published.';

CREATE TABLE document (
  doc_id                text PRIMARY KEY,
  deal_id               text NOT NULL REFERENCES deal,
  ontology_version      text NOT NULL,
  file_name             text NOT NULL,
  path                  text,
  format                text NOT NULL,
  doc_type              text NOT NULL,
  doc_type_confidence   numeric,
  version_group         text,                        -- versions of the same document share a group
  version_rank          int,                         -- 1 = latest
  is_primary            boolean NOT NULL DEFAULT true,
  in_data_room          boolean NOT NULL DEFAULT true,
  pointer_target_doc_id text REFERENCES document,    -- a "please see ..." note points to its target
  basis_default         text CHECK (basis_default IS NULL OR basis_default IN ('ACTUAL', 'BUDGET', 'FORECAST', 'MGMT_CASE', 'PRO_FORMA', 'ADJUSTED', 'MARKET_ESTIMATE', 'SURVEY')),
  evidence_tier         char(1) CHECK (evidence_tier IN ('A','B','C')),
  period_end            date,
  status                text NOT NULL CHECK (status IN ('READ','PARTIAL','SKIPPED','FAILED')),
  status_reason         text,
  facts_count           int NOT NULL DEFAULT 0,
  sha256                text,
  FOREIGN KEY (ontology_version, doc_type) REFERENCES onto_document_type (version, doc_type)
);
COMMENT ON TABLE document IS 'One data-room file. SKIPPED and FAILED files stay listed with the reason.';

CREATE TABLE source_location (
  location_id          text PRIMARY KEY,
  doc_id               text NOT NULL REFERENCES document,
  sheet_or_page        text,
  table_id             text,
  cell_range           text,                         -- spreadsheets: A1 range
  bbox                 numeric[],                    -- PDFs and slides: x0, y0, x1, y1
  row_label_as_read    text,
  column_label_as_read text,
  value_as_read        text,                         -- exactly as in the file, before any transform
  extraction_method    text NOT NULL,
  transform_steps      text[] NOT NULL DEFAULT '{}' -- e.g. scale x1000, sign flipped
);
COMMENT ON TABLE source_location IS 'Where a value was read: the lineage behind every source fact.';

CREATE TABLE dimension_member (
  deal_id          text NOT NULL REFERENCES deal,
  dimension        text NOT NULL,
  member_id        text NOT NULL,
  label            text NOT NULL,
  parent_member_id text,
  is_complete_set  boolean NOT NULL DEFAULT false,   -- true when the members add up to the total (enables rule R-DIM-01)
  aliases          text[] NOT NULL DEFAULT '{}',
  PRIMARY KEY (deal_id, dimension, member_id)
);
COMMENT ON TABLE dimension_member IS 'The splits a deal uses, e.g. service_line = Residential Sales.';

CREATE TABLE fact (
  fact_id              text PRIMARY KEY,
  deal_id              text NOT NULL REFERENCES deal,
  entity_id            text NOT NULL DEFAULT 'CONSOLIDATED',
  ontology_version     text NOT NULL REFERENCES onto_version,
  concept_id           text NOT NULL,                -- what the number is (must exist in the ontology)
  value                numeric,
  unit_type            text NOT NULL CHECK (unit_type IN ('CURRENCY', 'CURRENCY_PER_UNIT', 'COUNT', 'PERCENT', 'RATIO', 'MULTIPLE', 'DAYS', 'YEARS', 'VOLUME', 'MASS', 'SCORE', 'OTHER')),
  currency             char(3),
  scale_applied        bigint,
  unit_label           text,
  period_type          text NOT NULL CHECK (period_type IN ('FY', 'FH', 'FQ', 'FM', 'YTD', 'LTM', 'AS_AT', 'POINT')),
  period_start         date,
  period_end           date,
  months_covered       int,
  fiscal_year          int,
  basis                text NOT NULL CHECK (basis IN ('ACTUAL', 'BUDGET', 'FORECAST', 'MGMT_CASE', 'PRO_FORMA', 'ADJUSTED', 'MARKET_ESTIMATE', 'SURVEY')),
  dimensions           jsonb NOT NULL DEFAULT '{}',  -- e.g. {"service_line": "Residential Sales"}; empty = the total
  status               text NOT NULL CHECK (status IN ('CANDIDATE', 'SELECTED', 'COMPARATIVE', 'HELD', 'REJECTED', 'DERIVED')),
  reason_code          text,
  reason_detail        text,
  evidence_tier        char(1) NOT NULL CHECK (evidence_tier IN ('A','B','C')),
  doc_id               text REFERENCES document,
  authority_rank       int,
  source_location_ids  text[] NOT NULL DEFAULT '{}', -- where it was read (source facts)
  derived_from         text[] NOT NULL DEFAULT '{}', -- which facts it was computed from (derived facts)
  formula              text,
  comparative_fact_ids text[] NOT NULL DEFAULT '{}',
  mapping              jsonb,                        -- how the label was matched: method, confidence, classification
  extraction_run_id    text,
  reviewed_by          text,
  created_at           timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (ontology_version, concept_id)  REFERENCES onto_concept (version, concept_id),
  FOREIGN KEY (ontology_version, reason_code) REFERENCES onto_reason_code (version, code),
  CONSTRAINT fy_is_12_months     CHECK (period_type <> 'FY'  OR months_covered = 12),
  CONSTRAINT ytd_is_partial      CHECK (period_type <> 'YTD' OR months_covered BETWEEN 1 AND 11),
  CONSTRAINT currency_needs_code CHECK (unit_type <> 'CURRENCY' OR currency IS NOT NULL),
  CONSTRAINT held_needs_reason   CHECK (status NOT IN ('HELD','REJECTED','COMPARATIVE') OR reason_code IS NOT NULL),
  CONSTRAINT lineage_required    CHECK (cardinality(source_location_ids) > 0 OR cardinality(derived_from) > 0)
);
COMMENT ON TABLE fact IS 'One row per number. SELECTED = read and chosen; DERIVED = worked out by the calculations; COMPARATIVE = kept to check against; HELD = waiting for a person; REJECTED = not used.';
-- one chosen value per figure: at most one SELECTED or DERIVED fact per fact key
CREATE UNIQUE INDEX fact_key_selected ON fact (deal_id, entity_id, concept_id, period_type, coalesce(period_end, '1900-01-01'), basis, dimensions)
  WHERE status IN ('SELECTED','DERIVED');
CREATE INDEX fact_concept ON fact (deal_id, concept_id, period_end);
CREATE INDEX fact_dims    ON fact USING gin (dimensions);

CREATE TABLE record (
  record_id           text PRIMARY KEY,
  deal_id             text NOT NULL REFERENCES deal,
  ontology_version    text NOT NULL,
  record_class        text NOT NULL,                 -- facility, lease, adjustment, competitor, finding ...
  fields              jsonb NOT NULL,
  source_location_ids text[] NOT NULL DEFAULT '{}',
  evidence_tier       char(1),
  status              text NOT NULL DEFAULT 'CANDIDATE',
  FOREIGN KEY (ontology_version, record_class) REFERENCES onto_record_class (version, record_class)
);
CREATE INDEX record_class_idx ON record (deal_id, record_class);
COMMENT ON TABLE record IS 'Items that are not a single number. Numeric facts about a record carry its id as a dimension member (e.g. facility).';

CREATE TABLE reconciliation (
  recon_id            bigserial PRIMARY KEY,
  deal_id             text NOT NULL REFERENCES deal,
  selected_fact_id    text NOT NULL REFERENCES fact,
  comparative_fact_id text NOT NULL REFERENCES fact,
  variance            numeric NOT NULL,
  variance_pct        numeric,
  explanation         text,
  status              text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','EXPLAINED','ACCEPTED'))
);
COMMENT ON TABLE reconciliation IS 'A chosen value compared with another source for the same figure.';

CREATE TABLE flag (
  flag_id     text PRIMARY KEY,
  deal_id     text NOT NULL REFERENCES deal,
  code        text NOT NULL,                         -- rule id (R-..., P-...) or reason code
  severity    text NOT NULL CHECK (severity IN ('block','warn','flag')),
  materiality numeric,
  schedule_id text,
  fact_ids    text[] NOT NULL DEFAULT '{}',
  message     text,
  status      text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','RESOLVED','WAIVED'))
);
COMMENT ON TABLE flag IS 'A failed check. A block flag stops its databook tab publishing until fixed or waived by a named person.';

CREATE TABLE mapping_decision (
  mapping_id         bigserial PRIMARY KEY,
  deal_id            text NOT NULL REFERENCES deal,
  doc_id             text NOT NULL REFERENCES document,
  ontology_version   text NOT NULL,
  label_as_read      text NOT NULL,
  label_path         text[],                         -- headings above the line, outermost first
  concept_id         text NOT NULL,
  dimensions         jsonb NOT NULL DEFAULT '{}',
  method             text NOT NULL,                  -- EXACT, CONTAINS, SECTION_DEFAULT, MODEL, USER ...
  confidence         numeric,
  validated_by_rules text[] NOT NULL DEFAULT '{}',
  reviewer           text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (ontology_version, concept_id) REFERENCES onto_concept (version, concept_id)
);
COMMENT ON TABLE mapping_decision IS 'How each label was matched to a concept. Approved rows are the mapper''s training and regression set.';

-- ------------------------------------------------------------------------ PART C: views
CREATE VIEW v_databook_fact AS
SELECT f.deal_id, f.fact_id, f.concept_id, c.label AS concept_label, c.statement, c.schedules, f.dimensions,
       f.period_type, f.period_start, f.period_end, f.months_covered, f.basis, f.value, f.unit_type, f.currency,
       f.status, f.evidence_tier, f.formula,
       d.file_name, sl.sheet_or_page, sl.cell_range, sl.value_as_read
FROM fact f
JOIN onto_concept c ON c.version = f.ontology_version AND c.concept_id = f.concept_id
LEFT JOIN source_location sl ON sl.location_id = f.source_location_ids[1]
LEFT JOIN document d ON d.doc_id = sl.doc_id
WHERE f.status IN ('SELECTED','DERIVED');
COMMENT ON VIEW v_databook_fact IS 'The figures the databook may show, with the ontology label and the first source cell.';

CREATE VIEW v_open_flags AS
SELECT fl.deal_id, fl.code, r.description AS rule, fl.severity, fl.schedule_id, fl.message, fl.fact_ids
FROM flag fl JOIN deal dl ON dl.deal_id = fl.deal_id
LEFT JOIN onto_rule r ON r.version = dl.ontology_version AND r.rule_id = fl.code
WHERE fl.status = 'OPEN';
