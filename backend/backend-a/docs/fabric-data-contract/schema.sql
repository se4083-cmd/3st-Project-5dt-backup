-- Documentation extraction: NEW isolated local PostgreSQL 16.15
-- Applied existing migrations 0001 through head; no seed; schema only, no rows.
-- Azure deployment DB was NOT queried in this documentation task.
-- Owners/grants/environment-specific settings are intentionally not portable DDL.
--
-- PostgreSQL database dump
--

\restrict PihOaE6p3BBfUOmpSajgvDLKf0D2dUlagd5tUhyvs7X2uSS2UDkKHxSyWrGNxrM

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: csflow_analytics_head_immutable(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.csflow_analytics_head_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF OLD.status='SUCCEEDED' THEN
            IF TG_OP='DELETE' THEN RAISE EXCEPTION 'PUBLISHED_ANALYTICS_IMMUTABLE'; END IF;
            IF (to_jsonb(NEW)-'is_current') IS DISTINCT FROM (to_jsonb(OLD)-'is_current') THEN
              RAISE EXCEPTION 'PUBLISHED_ANALYTICS_IMMUTABLE';
            END IF;
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
        END $$;


--
-- Name: csflow_analytics_mart_immutable(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.csflow_analytics_mart_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE batch_status text;
        BEGIN
          IF TG_OP <> 'INSERT' THEN
            SELECT status INTO batch_status FROM analytics_batches WHERE batch_id=OLD.batch_id FOR SHARE;
            IF batch_status='SUCCEEDED' THEN RAISE EXCEPTION 'PUBLISHED_ANALYTICS_IMMUTABLE'; END IF;
          END IF;
          IF TG_OP <> 'DELETE' THEN
            SELECT status INTO batch_status FROM analytics_batches WHERE batch_id=NEW.batch_id FOR SHARE;
            IF batch_status='SUCCEEDED' THEN RAISE EXCEPTION 'PUBLISHED_ANALYTICS_IMMUTABLE'; END IF;
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
        END $$;


--
-- Name: csflow_analytics_receipt_immutable(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.csflow_analytics_receipt_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          PERFORM 1 FROM analytics_batches WHERE batch_id=OLD.batch_id FOR SHARE;
          IF TG_OP='DELETE' THEN RAISE EXCEPTION 'ANALYTICS_RECEIPT_IMMUTABLE'; END IF;
          IF NEW.payload IS DISTINCT FROM OLD.payload OR NEW.content_hash IS DISTINCT FROM OLD.content_hash OR
             NEW.batch_id IS DISTINCT FROM OLD.batch_id OR EXISTS(SELECT 1 FROM analytics_batches
             WHERE batch_id=OLD.batch_id AND status='SUCCEEDED') THEN
            RAISE EXCEPTION 'ANALYTICS_RECEIPT_IMMUTABLE';
          END IF;
          RETURN NEW;
        END $$;


--
-- Name: csflow_control_history_immutable(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.csflow_control_history_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN RAISE EXCEPTION 'CONTROL_HISTORY_IMMUTABLE'; END $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: ai_suggestions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_suggestions (
    suggestion_id uuid NOT NULL,
    ticket_id uuid,
    cycle_no bigint,
    revision bigint NOT NULL,
    category text NOT NULL,
    draft text NOT NULL,
    confidence numeric(4,3),
    evidence_refs jsonb,
    order_snapshot jsonb,
    gate_results jsonb,
    rule_id uuid NOT NULL,
    rule_version bigint NOT NULL,
    template_key text NOT NULL,
    prompt_version text NOT NULL,
    model_version text NOT NULL,
    content_hash text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: analytics_batches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analytics_batches (
    batch_id uuid NOT NULL,
    status text NOT NULL,
    source_as_of timestamp with time zone,
    published_at timestamp with time zone,
    row_counts jsonb NOT NULL,
    checksums jsonb NOT NULL,
    schema_version text NOT NULL,
    is_current boolean NOT NULL,
    manifest jsonb NOT NULL,
    data_origin text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    validation_passed boolean DEFAULT false NOT NULL,
    validated_at timestamp with time zone,
    content_hash character varying(64),
    CONSTRAINT ck_analytics_batches_current_success CHECK (((NOT is_current) OR ((status = 'SUCCEEDED'::text) AND (published_at IS NOT NULL) AND validation_passed AND (validated_at IS NOT NULL) AND (content_hash IS NOT NULL))))
);


--
-- Name: analytics_daily; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analytics_daily (
    batch_id uuid NOT NULL,
    day date NOT NULL,
    team_key text NOT NULL,
    category text NOT NULL,
    ticket_count bigint NOT NULL,
    auto_closed_count bigint NOT NULL,
    handoff_count bigint NOT NULL,
    reopened_count bigint NOT NULL,
    sla_breach_count bigint NOT NULL,
    duration_sum_seconds double precision NOT NULL,
    duration_n bigint NOT NULL,
    approval_count bigint NOT NULL,
    review_count bigint NOT NULL,
    data_origin text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: analytics_product_daily; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analytics_product_daily (
    batch_id uuid NOT NULL,
    day date NOT NULL,
    product_id uuid NOT NULL,
    category text NOT NULL,
    issue_tag text NOT NULL,
    ticket_count bigint NOT NULL,
    return_refund_count bigint NOT NULL,
    auto_count bigint NOT NULL,
    handoff_count bigint NOT NULL,
    paid_order_count bigint,
    inquiry_order_count bigint,
    prior_count bigint,
    data_origin text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: analytics_product_risk; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analytics_product_risk (
    batch_id uuid NOT NULL,
    scope_key text NOT NULL,
    product_id uuid NOT NULL,
    rule_version text NOT NULL,
    data_status text NOT NULL,
    score numeric(12,6),
    rank bigint,
    risk_band text,
    metrics jsonb NOT NULL,
    components jsonb NOT NULL,
    source_as_of timestamp with time zone,
    window_end timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_analytics_product_risk_eligible_values CHECK ((((data_status = 'ELIGIBLE'::text) AND (score IS NOT NULL) AND (rank IS NOT NULL) AND (risk_band IS NOT NULL) AND ((score >= (0)::numeric) AND (score <= (100)::numeric)) AND (rank > 0) AND (risk_band = ANY (ARRAY['NORMAL'::text, 'WATCH'::text, 'HIGH'::text]))) OR ((data_status = ANY (ARRAY['LOW_SAMPLE'::text, 'DATA_MISSING'::text, 'QUALITY_BLOCKED'::text])) AND (score IS NULL) AND (rank IS NULL) AND (risk_band IS NULL))))
);


--
-- Name: analytics_product_voc_daily; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analytics_product_voc_daily (
    batch_id uuid NOT NULL,
    scope_key text NOT NULL,
    product_id uuid NOT NULL,
    day date NOT NULL,
    primary_issue text NOT NULL,
    episode_count bigint NOT NULL,
    unresolved_count bigint NOT NULL,
    data_origin text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: analytics_publication; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analytics_publication (
    singleton_id integer NOT NULL,
    batch_id uuid,
    CONSTRAINT ck_analytics_publication_singleton CHECK ((singleton_id = 1))
);


--
-- Name: analytics_publication_singleton_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.analytics_publication_singleton_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: analytics_publication_singleton_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.analytics_publication_singleton_id_seq OWNED BY public.analytics_publication.singleton_id;


--
-- Name: analytics_receipts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analytics_receipts (
    batch_id uuid NOT NULL,
    content_hash character varying(64) NOT NULL,
    payload jsonb NOT NULL,
    validation_result jsonb NOT NULL,
    received_at timestamp with time zone NOT NULL
);


--
-- Name: approvals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approvals (
    approval_id uuid NOT NULL,
    ticket_id uuid,
    suggestion_id uuid NOT NULL,
    cycle_no bigint,
    ticket_version bigint NOT NULL,
    mode text NOT NULL,
    decision text NOT NULL,
    reviewer_id uuid,
    gate_snapshot jsonb,
    content_hash text NOT NULL,
    reviewed_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL
);


--
-- Name: assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assignments (
    assignment_id uuid NOT NULL,
    ticket_id uuid NOT NULL,
    cycle_no bigint NOT NULL,
    team_id uuid,
    agent_id uuid,
    assigned_at timestamp with time zone NOT NULL,
    ended_at timestamp with time zone,
    reason_code text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL,
    CONSTRAINT ck_assignments_cycle_time CHECK (((cycle_no >= 1) AND ((ended_at IS NULL) OR (ended_at >= assigned_at))))
);


--
-- Name: audit_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_events (
    event_id uuid NOT NULL,
    ticket_id uuid,
    cycle_no bigint,
    actor_user_id uuid,
    actor_service text,
    action text NOT NULL,
    target_type text NOT NULL,
    target_id uuid,
    event_key text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL,
    result character varying(16) DEFAULT 'SUCCESS'::character varying NOT NULL,
    reason_code character varying(64) DEFAULT 'FIXTURE_HISTORY'::character varying NOT NULL,
    CONSTRAINT ck_audit_events_result CHECK (((result)::text = ANY ((ARRAY['SUCCESS'::character varying, 'DENIED'::character varying, 'FAILURE'::character varying])::text[])))
);


--
-- Name: automation_control; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.automation_control (
    singleton_id integer NOT NULL,
    paused boolean DEFAULT false NOT NULL,
    revision bigint NOT NULL,
    generation bigint NOT NULL,
    reason_code character varying(64) NOT NULL,
    changed_by uuid,
    changed_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_automation_control_reason CHECK (((reason_code)::text = ANY ((ARRAY['INITIAL_STATE'::character varying, 'SAFETY_INCIDENT'::character varying, 'OPERATOR_PAUSE'::character varying, 'VERIFICATION_COMPLETE'::character varying, 'INCIDENT_RESOLVED'::character varying])::text[]))),
    CONSTRAINT ck_automation_control_singleton CHECK (((singleton_id = 1) AND (revision >= 1) AND (generation >= 1)))
);


--
-- Name: automation_control_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.automation_control_history (
    revision bigint NOT NULL,
    generation bigint NOT NULL,
    paused boolean NOT NULL,
    reason_code character varying(64) NOT NULL,
    changed_by uuid,
    changed_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_automation_control_history_reason CHECK (((reason_code)::text = ANY ((ARRAY['INITIAL_STATE'::character varying, 'SAFETY_INCIDENT'::character varying, 'OPERATOR_PAUSE'::character varying, 'VERIFICATION_COMPLETE'::character varying, 'INCIDENT_RESOLVED'::character varying])::text[]))),
    CONSTRAINT ck_automation_control_history_revision CHECK (((revision >= 1) AND (generation >= 1)))
);


--
-- Name: automation_control_history_revision_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.automation_control_history_revision_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: automation_control_history_revision_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.automation_control_history_revision_seq OWNED BY public.automation_control_history.revision;


--
-- Name: automation_control_singleton_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.automation_control_singleton_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: automation_control_singleton_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.automation_control_singleton_id_seq OWNED BY public.automation_control.singleton_id;


--
-- Name: automation_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.automation_jobs (
    job_id uuid NOT NULL,
    ticket_id uuid NOT NULL,
    cycle_no bigint NOT NULL,
    status text NOT NULL,
    attempt bigint NOT NULL,
    next_attempt_at timestamp with time zone NOT NULL,
    lease_token uuid,
    lease_until timestamp with time zone,
    error_code text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL,
    expected_ticket_version bigint NOT NULL,
    lease_owner character varying(128),
    job_kind character varying(16) DEFAULT 'AUTO'::character varying NOT NULL,
    source_message_id uuid,
    reason_code character varying(64),
    automation_generation bigint DEFAULT 1 NOT NULL,
    CONSTRAINT ck_automation_jobs_counters CHECK (((cycle_no >= 1) AND (attempt >= 0) AND (expected_ticket_version >= 1))),
    CONSTRAINT ck_automation_jobs_handoff_request CHECK (((((job_kind)::text = 'AUTO'::text) AND (reason_code IS NULL)) OR (((job_kind)::text = 'HANDOFF'::text) AND (source_message_id IS NOT NULL) AND (reason_code IS NOT NULL) AND ((reason_code)::text = ANY ((ARRAY['CUSTOMER_REQUEST'::character varying, 'DISSATISFIED'::character varying, 'COMPLEX_ISSUE'::character varying, 'OTHER'::character varying, 'HUMAN_CONTINUATION'::character varying])::text[]))))),
    CONSTRAINT ck_automation_jobs_kind CHECK (((job_kind)::text = ANY ((ARRAY['AUTO'::character varying, 'HANDOFF'::character varying])::text[]))),
    CONSTRAINT ck_automation_jobs_lease CHECK ((((status = 'RUNNING'::text) AND (lease_token IS NOT NULL) AND (lease_until IS NOT NULL) AND (lease_owner IS NOT NULL)) OR ((status <> 'RUNNING'::text) AND (lease_token IS NULL) AND (lease_until IS NULL) AND (lease_owner IS NULL)))),
    CONSTRAINT ck_automation_jobs_state CHECK ((status = ANY (ARRAY['PENDING'::text, 'RUNNING'::text, 'RETRY'::text, 'SUCCEEDED'::text, 'FAILED'::text, 'HANDED_OFF'::text, 'CANCELLED'::text])))
);


--
-- Name: automation_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.automation_rules (
    rule_id uuid NOT NULL,
    rule_key text NOT NULL,
    version bigint NOT NULL,
    category text NOT NULL,
    risk_level text NOT NULL,
    requires_approval boolean NOT NULL,
    conditions jsonb NOT NULL,
    active boolean NOT NULL,
    updated_by uuid,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL
);


--
-- Name: customers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customers (
    customer_id uuid NOT NULL,
    user_id uuid NOT NULL,
    display_name text NOT NULL,
    verification_status text NOT NULL,
    profile_masked jsonb,
    deleted_at timestamp with time zone,
    customer_key text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL
);


--
-- Name: followup_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.followup_actions (
    action_id uuid NOT NULL,
    ticket_id uuid,
    cycle_no bigint,
    product_id uuid,
    owner_user_id uuid,
    owner_team_id uuid NOT NULL,
    kind text NOT NULL,
    status text NOT NULL,
    public_note text,
    internal_note text,
    blocks_resolution boolean NOT NULL,
    due_at timestamp with time zone,
    completed_at timestamp with time zone,
    version bigint NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL,
    origin_team_id uuid NOT NULL,
    responsibility_cycle_no bigint,
    cancelled_at timestamp with time zone,
    cancellation_reason character varying(64),
    CONSTRAINT ck_followup_actions_cancelled CHECK ((((status = 'CANCELLED'::text) AND (cancelled_at IS NOT NULL) AND (cancellation_reason IS NOT NULL) AND ((cancellation_reason)::text = ANY ((ARRAY['CUSTOMER_WITHDREW'::character varying, 'NO_LONGER_NEEDED'::character varying, 'DUPLICATE'::character varying, 'OTHER'::character varying])::text[]))) OR ((status <> 'CANCELLED'::text) AND (cancelled_at IS NULL) AND (cancellation_reason IS NULL)))),
    CONSTRAINT ck_followup_actions_completed CHECK ((((status = 'DONE'::text) AND (completed_at IS NOT NULL)) OR ((status <> 'DONE'::text) AND (completed_at IS NULL)))),
    CONSTRAINT ck_followup_actions_cycle CHECK ((((ticket_id IS NOT NULL) AND (cycle_no IS NOT NULL) AND (cycle_no >= 1) AND (responsibility_cycle_no IS NOT NULL) AND (responsibility_cycle_no >= cycle_no)) OR ((product_id IS NOT NULL) AND (cycle_no IS NULL) AND (responsibility_cycle_no IS NULL)))),
    CONSTRAINT ck_followup_actions_due CHECK (((due_at IS NULL) OR (due_at >= created_at))),
    CONSTRAINT ck_followup_actions_notes CHECK ((((public_note IS NULL) OR (length(public_note) <= 4000)) AND ((internal_note IS NULL) OR (length(internal_note) <= 10000)))),
    CONSTRAINT ck_followup_actions_product_block CHECK (((product_id IS NULL) OR (NOT blocks_resolution))),
    CONSTRAINT ck_followup_actions_state CHECK ((status = ANY (ARRAY['OPEN'::text, 'IN_PROGRESS'::text, 'DONE'::text, 'CANCELLED'::text]))),
    CONSTRAINT ck_followup_actions_target CHECK ((((ticket_id IS NULL) AND (product_id IS NOT NULL)) OR ((ticket_id IS NOT NULL) AND (product_id IS NULL)))),
    CONSTRAINT ck_followup_actions_version CHECK ((version >= 1))
);


--
-- Name: idempotency_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.idempotency_keys (
    user_id uuid NOT NULL,
    key character varying(128) NOT NULL,
    request_hash character varying(64) NOT NULL,
    ticket_id uuid,
    created_at timestamp with time zone NOT NULL,
    operation character varying(32) DEFAULT 'CREATE_TICKET'::character varying NOT NULL,
    response_snapshot jsonb,
    followup_id uuid,
    CONSTRAINT ck_idempotency_keys_operation CHECK (((operation)::text = ANY ((ARRAY['CREATE_TICKET'::character varying, 'REOPEN'::character varying, 'REQUEST_AGENT'::character varying, 'FOLLOWUP_CREATE'::character varying])::text[]))),
    CONSTRAINT ck_idempotency_keys_snapshot CHECK ((((operation)::text = 'CREATE_TICKET'::text) OR (response_snapshot IS NOT NULL))),
    CONSTRAINT ck_idempotency_keys_target CHECK (((((operation)::text = 'FOLLOWUP_CREATE'::text) AND (followup_id IS NOT NULL) AND (ticket_id IS NULL)) OR (((operation)::text <> 'FOLLOWUP_CREATE'::text) AND (followup_id IS NULL) AND (ticket_id IS NOT NULL))))
);


--
-- Name: knowledge_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_documents (
    document_id uuid NOT NULL,
    policy_key text NOT NULL,
    title text NOT NULL,
    version bigint NOT NULL,
    source text NOT NULL,
    blob_path text NOT NULL,
    content_hash text NOT NULL,
    allowed_topics jsonb NOT NULL,
    active boolean NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    effective_to timestamp with time zone,
    body text NOT NULL,
    approval_status text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL
);


--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    message_id uuid NOT NULL,
    ticket_id uuid NOT NULL,
    cycle_no bigint NOT NULL,
    role text NOT NULL,
    direction text NOT NULL,
    body text NOT NULL,
    approval_id uuid,
    idempotency_key text,
    final_reply boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL,
    visibility character varying(16) DEFAULT 'INTERNAL'::character varying NOT NULL,
    CONSTRAINT ck_messages_body CHECK (((length(TRIM(BOTH FROM body)) >= 1) AND (length(TRIM(BOTH FROM body)) <= 10000))),
    CONSTRAINT ck_messages_cycle CHECK ((cycle_no >= 1)),
    CONSTRAINT ck_messages_direction CHECK ((direction = ANY (ARRAY['IN'::text, 'OUT'::text, 'INTERNAL'::text]))),
    CONSTRAINT ck_messages_public_shape CHECK ((((visibility)::text <> 'PUBLIC'::text) OR (((role = 'CUSTOMER'::text) AND (direction = 'IN'::text)) OR ((role = ANY (ARRAY['AGENT'::text, 'ASSISTANT'::text, 'SYSTEM'::text])) AND (direction = 'OUT'::text))))),
    CONSTRAINT ck_messages_role CHECK ((role = ANY (ARRAY['CUSTOMER'::text, 'AGENT'::text, 'ASSISTANT'::text, 'SYSTEM'::text]))),
    CONSTRAINT ck_messages_visibility CHECK (((visibility)::text = ANY ((ARRAY['PUBLIC'::character varying, 'INTERNAL'::character varying])::text[])))
);


--
-- Name: orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orders (
    order_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    product_id uuid,
    quantity bigint NOT NULL,
    order_number text NOT NULL,
    order_status text NOT NULL,
    payment_status text NOT NULL,
    amount numeric(12,2) NOT NULL,
    placed_at timestamp with time zone NOT NULL,
    paid_at timestamp with time zone,
    version bigint NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL,
    CONSTRAINT ck_orders_quantity_amount CHECK (((quantity > 0) AND (amount >= (0)::numeric) AND (version >= 1)))
);


--
-- Name: products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.products (
    product_id uuid NOT NULL,
    sku text NOT NULL,
    name text NOT NULL,
    category text NOT NULL,
    active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL
);


--
-- Name: queue_routes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.queue_routes (
    ticket_id uuid NOT NULL,
    cycle_no bigint NOT NULL,
    team_id uuid,
    revision bigint NOT NULL,
    recorded_by_service character varying(64) NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_queue_routes_revision CHECK (((cycle_no >= 1) AND (revision >= 1)))
);


--
-- Name: returns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.returns (
    return_id uuid NOT NULL,
    order_id uuid,
    status text NOT NULL,
    requested_at timestamp with time zone NOT NULL,
    reason text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL
);


--
-- Name: shipments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shipments (
    shipment_id uuid NOT NULL,
    order_id uuid,
    status text NOT NULL,
    eta_if_known text,
    state_changed_at timestamp with time zone NOT NULL,
    version bigint NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL
);


--
-- Name: staff_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.staff_permissions (
    user_id uuid NOT NULL,
    permission character varying(64) NOT NULL,
    granted_by uuid,
    granted_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_staff_permissions_permission CHECK (((permission)::text = ANY ((ARRAY['EXCEPTION_QUEUE_READ'::character varying, 'UNROUTED_QUEUE_READ'::character varying, 'AUTOMATION_READ'::character varying, 'AUTOMATION_STOP'::character varying, 'AUTOMATION_RESUME'::character varying, 'RETENTION_TEAM_REVIEW'::character varying, 'RETENTION_GLOBAL_REVIEW'::character varying])::text[])))
);


--
-- Name: team_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.team_categories (
    team_id uuid NOT NULL,
    category character varying(32) NOT NULL
);


--
-- Name: teams; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.teams (
    team_id uuid NOT NULL,
    name text NOT NULL,
    supported_categories jsonb NOT NULL,
    active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL
);


--
-- Name: tickets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tickets (
    ticket_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    order_id uuid,
    product_id uuid,
    category text NOT NULL,
    priority text NOT NULL,
    status text NOT NULL,
    version bigint NOT NULL,
    cycle_no bigint NOT NULL,
    requested_mode text NOT NULL,
    resolution_mode text,
    issue_tags jsonb NOT NULL,
    sla_due_at timestamp with time zone NOT NULL,
    first_replied_at timestamp with time zone,
    resolved_at timestamp with time zone,
    last_error_code text,
    is_complaint boolean NOT NULL,
    primary_issue text,
    complaint_first_at timestamp with time zone,
    voc_label_version text,
    voc_label_source text,
    label_status text NOT NULL,
    human_verified boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL,
    team_id uuid,
    CONSTRAINT ck_tickets_order_product CHECK (((order_id IS NULL) OR (product_id IS NOT NULL))),
    CONSTRAINT ck_tickets_requested_mode CHECK ((requested_mode = ANY (ARRAY['AUTO'::text, 'HUMAN'::text]))),
    CONSTRAINT ck_tickets_resolution_mode CHECK (((resolution_mode IS NULL) OR (resolution_mode = ANY (ARRAY['AUTO'::text, 'HUMAN'::text])))),
    CONSTRAINT ck_tickets_resolved_at CHECK (((status <> 'RESOLVED'::text) OR ((resolved_at IS NOT NULL) AND (resolution_mode IS NOT NULL)))),
    CONSTRAINT ck_tickets_status CHECK ((status = ANY (ARRAY['OPEN'::text, 'PROCESSING'::text, 'WAITING_CUSTOMER'::text, 'HANDOFF_PENDING'::text, 'ASSIGNED'::text, 'IN_PROGRESS'::text, 'FOLLOWUP_PENDING'::text, 'RESOLVED'::text, 'CANCELLED'::text]))),
    CONSTRAINT ck_tickets_version_cycle CHECK (((version >= 1) AND (cycle_no >= 1)))
);


--
-- Name: user_team_scopes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_team_scopes (
    user_id uuid NOT NULL,
    team_id uuid NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    user_id uuid NOT NULL,
    login_name text NOT NULL,
    password_hash text NOT NULL,
    role text NOT NULL,
    team_id uuid,
    allowed_team_ids jsonb NOT NULL,
    active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    data_origin text NOT NULL,
    scenario_id text NOT NULL,
    generator_version text NOT NULL,
    seed bigint NOT NULL,
    is_dev_account boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_users_role CHECK ((role = ANY (ARRAY['CUSTOMER'::text, 'AGENT'::text, 'ADMIN'::text])))
);


--
-- Name: analytics_publication singleton_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_publication ALTER COLUMN singleton_id SET DEFAULT nextval('public.analytics_publication_singleton_id_seq'::regclass);


--
-- Name: automation_control singleton_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_control ALTER COLUMN singleton_id SET DEFAULT nextval('public.automation_control_singleton_id_seq'::regclass);


--
-- Name: automation_control_history revision; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_control_history ALTER COLUMN revision SET DEFAULT nextval('public.automation_control_history_revision_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: ai_suggestions pk_ai_suggestions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_suggestions
    ADD CONSTRAINT pk_ai_suggestions PRIMARY KEY (suggestion_id);


--
-- Name: analytics_batches pk_analytics_batches; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_batches
    ADD CONSTRAINT pk_analytics_batches PRIMARY KEY (batch_id);


--
-- Name: analytics_daily pk_analytics_daily; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_daily
    ADD CONSTRAINT pk_analytics_daily PRIMARY KEY (batch_id, day, team_key, category);


--
-- Name: analytics_product_daily pk_analytics_product_daily; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_product_daily
    ADD CONSTRAINT pk_analytics_product_daily PRIMARY KEY (batch_id, day, product_id, category, issue_tag);


--
-- Name: analytics_product_risk pk_analytics_product_risk; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_product_risk
    ADD CONSTRAINT pk_analytics_product_risk PRIMARY KEY (batch_id, scope_key, product_id);


--
-- Name: analytics_product_voc_daily pk_analytics_product_voc_daily; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_product_voc_daily
    ADD CONSTRAINT pk_analytics_product_voc_daily PRIMARY KEY (batch_id, scope_key, product_id, day, primary_issue);


--
-- Name: analytics_publication pk_analytics_publication; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_publication
    ADD CONSTRAINT pk_analytics_publication PRIMARY KEY (singleton_id);


--
-- Name: analytics_receipts pk_analytics_receipts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_receipts
    ADD CONSTRAINT pk_analytics_receipts PRIMARY KEY (batch_id);


--
-- Name: approvals pk_approvals; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT pk_approvals PRIMARY KEY (approval_id);


--
-- Name: assignments pk_assignments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assignments
    ADD CONSTRAINT pk_assignments PRIMARY KEY (assignment_id);


--
-- Name: audit_events pk_audit_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT pk_audit_events PRIMARY KEY (event_id);


--
-- Name: automation_control pk_automation_control; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_control
    ADD CONSTRAINT pk_automation_control PRIMARY KEY (singleton_id);


--
-- Name: automation_control_history pk_automation_control_history; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_control_history
    ADD CONSTRAINT pk_automation_control_history PRIMARY KEY (revision);


--
-- Name: automation_jobs pk_automation_jobs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_jobs
    ADD CONSTRAINT pk_automation_jobs PRIMARY KEY (job_id);


--
-- Name: automation_rules pk_automation_rules; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_rules
    ADD CONSTRAINT pk_automation_rules PRIMARY KEY (rule_id);


--
-- Name: customers pk_customers; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT pk_customers PRIMARY KEY (customer_id);


--
-- Name: followup_actions pk_followup_actions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.followup_actions
    ADD CONSTRAINT pk_followup_actions PRIMARY KEY (action_id);


--
-- Name: idempotency_keys pk_idempotency_keys; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_keys
    ADD CONSTRAINT pk_idempotency_keys PRIMARY KEY (user_id, key);


--
-- Name: knowledge_documents pk_knowledge_documents; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_documents
    ADD CONSTRAINT pk_knowledge_documents PRIMARY KEY (document_id);


--
-- Name: messages pk_messages; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT pk_messages PRIMARY KEY (message_id);


--
-- Name: orders pk_orders; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT pk_orders PRIMARY KEY (order_id);


--
-- Name: products pk_products; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT pk_products PRIMARY KEY (product_id);


--
-- Name: queue_routes pk_queue_routes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.queue_routes
    ADD CONSTRAINT pk_queue_routes PRIMARY KEY (ticket_id, cycle_no);


--
-- Name: returns pk_returns; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.returns
    ADD CONSTRAINT pk_returns PRIMARY KEY (return_id);


--
-- Name: shipments pk_shipments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT pk_shipments PRIMARY KEY (shipment_id);


--
-- Name: staff_permissions pk_staff_permissions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_permissions
    ADD CONSTRAINT pk_staff_permissions PRIMARY KEY (user_id, permission);


--
-- Name: team_categories pk_team_categories; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_categories
    ADD CONSTRAINT pk_team_categories PRIMARY KEY (team_id, category);


--
-- Name: teams pk_teams; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT pk_teams PRIMARY KEY (team_id);


--
-- Name: tickets pk_tickets; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT pk_tickets PRIMARY KEY (ticket_id);


--
-- Name: user_team_scopes pk_user_team_scopes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_team_scopes
    ADD CONSTRAINT pk_user_team_scopes PRIMARY KEY (user_id, team_id);


--
-- Name: users pk_users; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT pk_users PRIMARY KEY (user_id);


--
-- Name: ai_suggestions uq_ai_suggestions_ticket_id_cycle_no_revision; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_suggestions
    ADD CONSTRAINT uq_ai_suggestions_ticket_id_cycle_no_revision UNIQUE (ticket_id, cycle_no, revision);


--
-- Name: audit_events uq_audit_events_event_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT uq_audit_events_event_key UNIQUE (event_key);


--
-- Name: automation_jobs uq_automation_jobs_ticket_id_cycle_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_jobs
    ADD CONSTRAINT uq_automation_jobs_ticket_id_cycle_no UNIQUE (ticket_id, cycle_no);


--
-- Name: automation_rules uq_automation_rules_rule_key_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_rules
    ADD CONSTRAINT uq_automation_rules_rule_key_version UNIQUE (rule_key, version);


--
-- Name: customers uq_customers_customer_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT uq_customers_customer_key UNIQUE (customer_key);


--
-- Name: customers uq_customers_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT uq_customers_user_id UNIQUE (user_id);


--
-- Name: knowledge_documents uq_knowledge_documents_policy_key_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_documents
    ADD CONSTRAINT uq_knowledge_documents_policy_key_version UNIQUE (policy_key, version);


--
-- Name: orders uq_orders_order_id_customer_id_product_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT uq_orders_order_id_customer_id_product_id UNIQUE (order_id, customer_id, product_id);


--
-- Name: orders uq_orders_order_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT uq_orders_order_number UNIQUE (order_number);


--
-- Name: products uq_products_sku; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT uq_products_sku UNIQUE (sku);


--
-- Name: returns uq_returns_order_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.returns
    ADD CONSTRAINT uq_returns_order_id UNIQUE (order_id);


--
-- Name: shipments uq_shipments_order_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT uq_shipments_order_id UNIQUE (order_id);


--
-- Name: users uq_users_login_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_login_name UNIQUE (login_name);


--
-- Name: ix_assignments_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_assignments_agent ON public.assignments USING btree (agent_id, ticket_id, ended_at);


--
-- Name: ix_followups_team_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_followups_team_page ON public.followup_actions USING btree (owner_team_id, created_at, action_id);


--
-- Name: ix_followups_ticket; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_followups_ticket ON public.followup_actions USING btree (ticket_id, status, blocks_resolution);


--
-- Name: ix_jobs_recovery; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_recovery ON public.automation_jobs USING btree (status, next_attempt_at, job_id);


--
-- Name: ix_messages_ticket_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_messages_ticket_page ON public.messages USING btree (ticket_id, created_at, message_id);


--
-- Name: ix_orders_customer_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_customer_page ON public.orders USING btree (customer_id, placed_at, order_id);


--
-- Name: ix_tickets_customer_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tickets_customer_page ON public.tickets USING btree (customer_id, created_at, ticket_id);


--
-- Name: ix_tickets_team; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tickets_team ON public.tickets USING btree (team_id, created_at, ticket_id);


--
-- Name: uq_analytics_current; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_analytics_current ON public.analytics_batches USING btree (is_current) WHERE is_current;


--
-- Name: uq_assignments_current; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_assignments_current ON public.assignments USING btree (ticket_id) WHERE (ended_at IS NULL);


--
-- Name: uq_messages_final_cycle; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_messages_final_cycle ON public.messages USING btree (ticket_id, cycle_no) WHERE (final_reply AND (direction = 'OUT'::text));


--
-- Name: uq_risk_rank; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_risk_rank ON public.analytics_product_risk USING btree (batch_id, scope_key, rank) WHERE (rank IS NOT NULL);


--
-- Name: automation_control_history immutable_history; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER immutable_history BEFORE DELETE OR UPDATE ON public.automation_control_history FOR EACH ROW EXECUTE FUNCTION public.csflow_control_history_immutable();


--
-- Name: analytics_batches immutable_published; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER immutable_published BEFORE DELETE OR UPDATE ON public.analytics_batches FOR EACH ROW EXECUTE FUNCTION public.csflow_analytics_head_immutable();


--
-- Name: analytics_daily immutable_published; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER immutable_published BEFORE INSERT OR DELETE OR UPDATE ON public.analytics_daily FOR EACH ROW EXECUTE FUNCTION public.csflow_analytics_mart_immutable();


--
-- Name: analytics_product_daily immutable_published; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER immutable_published BEFORE INSERT OR DELETE OR UPDATE ON public.analytics_product_daily FOR EACH ROW EXECUTE FUNCTION public.csflow_analytics_mart_immutable();


--
-- Name: analytics_product_risk immutable_published; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER immutable_published BEFORE INSERT OR DELETE OR UPDATE ON public.analytics_product_risk FOR EACH ROW EXECUTE FUNCTION public.csflow_analytics_mart_immutable();


--
-- Name: analytics_product_voc_daily immutable_published; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER immutable_published BEFORE INSERT OR DELETE OR UPDATE ON public.analytics_product_voc_daily FOR EACH ROW EXECUTE FUNCTION public.csflow_analytics_mart_immutable();


--
-- Name: analytics_receipts immutable_receipt; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER immutable_receipt BEFORE DELETE OR UPDATE ON public.analytics_receipts FOR EACH ROW EXECUTE FUNCTION public.csflow_analytics_receipt_immutable();


--
-- Name: ai_suggestions fk_ai_suggestions_rule_id_automation_rules; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_suggestions
    ADD CONSTRAINT fk_ai_suggestions_rule_id_automation_rules FOREIGN KEY (rule_id) REFERENCES public.automation_rules(rule_id);


--
-- Name: ai_suggestions fk_ai_suggestions_ticket_id_tickets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_suggestions
    ADD CONSTRAINT fk_ai_suggestions_ticket_id_tickets FOREIGN KEY (ticket_id) REFERENCES public.tickets(ticket_id);


--
-- Name: analytics_daily fk_analytics_daily_batch_id_analytics_batches; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_daily
    ADD CONSTRAINT fk_analytics_daily_batch_id_analytics_batches FOREIGN KEY (batch_id) REFERENCES public.analytics_batches(batch_id);


--
-- Name: analytics_product_daily fk_analytics_product_daily_batch_id_analytics_batches; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_product_daily
    ADD CONSTRAINT fk_analytics_product_daily_batch_id_analytics_batches FOREIGN KEY (batch_id) REFERENCES public.analytics_batches(batch_id);


--
-- Name: analytics_product_daily fk_analytics_product_daily_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_product_daily
    ADD CONSTRAINT fk_analytics_product_daily_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(product_id);


--
-- Name: analytics_product_risk fk_analytics_product_risk_batch_id_analytics_batches; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_product_risk
    ADD CONSTRAINT fk_analytics_product_risk_batch_id_analytics_batches FOREIGN KEY (batch_id) REFERENCES public.analytics_batches(batch_id);


--
-- Name: analytics_product_risk fk_analytics_product_risk_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_product_risk
    ADD CONSTRAINT fk_analytics_product_risk_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(product_id);


--
-- Name: analytics_product_voc_daily fk_analytics_product_voc_daily_batch_id_analytics_batches; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_product_voc_daily
    ADD CONSTRAINT fk_analytics_product_voc_daily_batch_id_analytics_batches FOREIGN KEY (batch_id) REFERENCES public.analytics_batches(batch_id);


--
-- Name: analytics_product_voc_daily fk_analytics_product_voc_daily_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_product_voc_daily
    ADD CONSTRAINT fk_analytics_product_voc_daily_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(product_id);


--
-- Name: analytics_publication fk_analytics_publication_batch_id_analytics_receipts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_publication
    ADD CONSTRAINT fk_analytics_publication_batch_id_analytics_receipts FOREIGN KEY (batch_id) REFERENCES public.analytics_receipts(batch_id);


--
-- Name: analytics_receipts fk_analytics_receipts_batch_id_analytics_batches; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_receipts
    ADD CONSTRAINT fk_analytics_receipts_batch_id_analytics_batches FOREIGN KEY (batch_id) REFERENCES public.analytics_batches(batch_id);


--
-- Name: approvals fk_approvals_reviewer_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT fk_approvals_reviewer_id_users FOREIGN KEY (reviewer_id) REFERENCES public.users(user_id);


--
-- Name: approvals fk_approvals_suggestion_id_ai_suggestions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT fk_approvals_suggestion_id_ai_suggestions FOREIGN KEY (suggestion_id) REFERENCES public.ai_suggestions(suggestion_id);


--
-- Name: approvals fk_approvals_ticket_id_tickets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT fk_approvals_ticket_id_tickets FOREIGN KEY (ticket_id) REFERENCES public.tickets(ticket_id);


--
-- Name: assignments fk_assignments_agent_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assignments
    ADD CONSTRAINT fk_assignments_agent_id_users FOREIGN KEY (agent_id) REFERENCES public.users(user_id);


--
-- Name: assignments fk_assignments_team_id_teams; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assignments
    ADD CONSTRAINT fk_assignments_team_id_teams FOREIGN KEY (team_id) REFERENCES public.teams(team_id);


--
-- Name: assignments fk_assignments_ticket_id_tickets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assignments
    ADD CONSTRAINT fk_assignments_ticket_id_tickets FOREIGN KEY (ticket_id) REFERENCES public.tickets(ticket_id);


--
-- Name: audit_events fk_audit_events_actor_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT fk_audit_events_actor_user_id_users FOREIGN KEY (actor_user_id) REFERENCES public.users(user_id);


--
-- Name: audit_events fk_audit_events_ticket_id_tickets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT fk_audit_events_ticket_id_tickets FOREIGN KEY (ticket_id) REFERENCES public.tickets(ticket_id);


--
-- Name: automation_control fk_automation_control_changed_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_control
    ADD CONSTRAINT fk_automation_control_changed_by_users FOREIGN KEY (changed_by) REFERENCES public.users(user_id);


--
-- Name: automation_control_history fk_automation_control_history_changed_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_control_history
    ADD CONSTRAINT fk_automation_control_history_changed_by_users FOREIGN KEY (changed_by) REFERENCES public.users(user_id);


--
-- Name: automation_jobs fk_automation_jobs_source_message_id_messages; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_jobs
    ADD CONSTRAINT fk_automation_jobs_source_message_id_messages FOREIGN KEY (source_message_id) REFERENCES public.messages(message_id);


--
-- Name: automation_jobs fk_automation_jobs_ticket_id_tickets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_jobs
    ADD CONSTRAINT fk_automation_jobs_ticket_id_tickets FOREIGN KEY (ticket_id) REFERENCES public.tickets(ticket_id);


--
-- Name: automation_rules fk_automation_rules_updated_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_rules
    ADD CONSTRAINT fk_automation_rules_updated_by_users FOREIGN KEY (updated_by) REFERENCES public.users(user_id);


--
-- Name: customers fk_customers_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT fk_customers_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(user_id);


--
-- Name: followup_actions fk_followup_actions_origin_team_id_teams; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.followup_actions
    ADD CONSTRAINT fk_followup_actions_origin_team_id_teams FOREIGN KEY (origin_team_id) REFERENCES public.teams(team_id);


--
-- Name: followup_actions fk_followup_actions_owner_team_id_teams; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.followup_actions
    ADD CONSTRAINT fk_followup_actions_owner_team_id_teams FOREIGN KEY (owner_team_id) REFERENCES public.teams(team_id);


--
-- Name: followup_actions fk_followup_actions_owner_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.followup_actions
    ADD CONSTRAINT fk_followup_actions_owner_user_id_users FOREIGN KEY (owner_user_id) REFERENCES public.users(user_id);


--
-- Name: followup_actions fk_followup_actions_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.followup_actions
    ADD CONSTRAINT fk_followup_actions_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(product_id);


--
-- Name: followup_actions fk_followup_actions_ticket_id_tickets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.followup_actions
    ADD CONSTRAINT fk_followup_actions_ticket_id_tickets FOREIGN KEY (ticket_id) REFERENCES public.tickets(ticket_id);


--
-- Name: idempotency_keys fk_idempotency_keys_followup_id_followup_actions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_keys
    ADD CONSTRAINT fk_idempotency_keys_followup_id_followup_actions FOREIGN KEY (followup_id) REFERENCES public.followup_actions(action_id);


--
-- Name: idempotency_keys fk_idempotency_keys_ticket_id_tickets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_keys
    ADD CONSTRAINT fk_idempotency_keys_ticket_id_tickets FOREIGN KEY (ticket_id) REFERENCES public.tickets(ticket_id);


--
-- Name: idempotency_keys fk_idempotency_keys_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_keys
    ADD CONSTRAINT fk_idempotency_keys_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(user_id);


--
-- Name: messages fk_messages_approval_id_approvals; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT fk_messages_approval_id_approvals FOREIGN KEY (approval_id) REFERENCES public.approvals(approval_id);


--
-- Name: messages fk_messages_ticket_id_tickets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT fk_messages_ticket_id_tickets FOREIGN KEY (ticket_id) REFERENCES public.tickets(ticket_id);


--
-- Name: orders fk_orders_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_customer_id_customers FOREIGN KEY (customer_id) REFERENCES public.customers(customer_id);


--
-- Name: orders fk_orders_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(product_id);


--
-- Name: queue_routes fk_queue_routes_team_id_teams; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.queue_routes
    ADD CONSTRAINT fk_queue_routes_team_id_teams FOREIGN KEY (team_id) REFERENCES public.teams(team_id);


--
-- Name: queue_routes fk_queue_routes_ticket_id_tickets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.queue_routes
    ADD CONSTRAINT fk_queue_routes_ticket_id_tickets FOREIGN KEY (ticket_id) REFERENCES public.tickets(ticket_id);


--
-- Name: returns fk_returns_order_id_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.returns
    ADD CONSTRAINT fk_returns_order_id_orders FOREIGN KEY (order_id) REFERENCES public.orders(order_id);


--
-- Name: shipments fk_shipments_order_id_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT fk_shipments_order_id_orders FOREIGN KEY (order_id) REFERENCES public.orders(order_id);


--
-- Name: staff_permissions fk_staff_permissions_granted_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_permissions
    ADD CONSTRAINT fk_staff_permissions_granted_by_users FOREIGN KEY (granted_by) REFERENCES public.users(user_id);


--
-- Name: staff_permissions fk_staff_permissions_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_permissions
    ADD CONSTRAINT fk_staff_permissions_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(user_id);


--
-- Name: team_categories fk_team_categories_team_id_teams; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_categories
    ADD CONSTRAINT fk_team_categories_team_id_teams FOREIGN KEY (team_id) REFERENCES public.teams(team_id);


--
-- Name: tickets fk_tickets_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT fk_tickets_customer_id_customers FOREIGN KEY (customer_id) REFERENCES public.customers(customer_id);


--
-- Name: tickets fk_tickets_owned_order_product; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT fk_tickets_owned_order_product FOREIGN KEY (order_id, customer_id, product_id) REFERENCES public.orders(order_id, customer_id, product_id);


--
-- Name: tickets fk_tickets_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT fk_tickets_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(product_id);


--
-- Name: tickets fk_tickets_team_id_teams; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT fk_tickets_team_id_teams FOREIGN KEY (team_id) REFERENCES public.teams(team_id);


--
-- Name: user_team_scopes fk_user_team_scopes_team_id_teams; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_team_scopes
    ADD CONSTRAINT fk_user_team_scopes_team_id_teams FOREIGN KEY (team_id) REFERENCES public.teams(team_id);


--
-- Name: user_team_scopes fk_user_team_scopes_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_team_scopes
    ADD CONSTRAINT fk_user_team_scopes_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(user_id);


--
-- Name: users fk_users_team_id_teams; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_team_id_teams FOREIGN KEY (team_id) REFERENCES public.teams(team_id);


--
-- PostgreSQL database dump complete
--

\unrestrict PihOaE6p3BBfUOmpSajgvDLKf0D2dUlagd5tUhyvs7X2uSS2UDkKHxSyWrGNxrM

