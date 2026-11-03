-- Oracle relational table/index reference through vk0014 (2026-11-03); NOT an install script.
-- Generated from current ORM metadata plus SDK owner lock metadata.
-- Physical upgraded column types/constraints follow migration history, not create_all output.
-- Install/upgrade with Alembic. vk0008/vk0011 initialize knowledge/graph audit triggers.
-- vk0014 principle history is application-transactional, not direct-SQL trigger auditing.
-- RDF, SQL Property Graph and optional SDK native objects need separate initialization.
-- vk_alembic_version and native graph/SDK objects are intentionally not listed here.

CREATE TABLE vk_item (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	title VARCHAR2(300 CHAR) NOT NULL,
	knowledge_type VARCHAR2(40 CHAR) NOT NULL,
	category VARCHAR2(120 CHAR),
	tags_json CLOB NOT NULL,
	active_revision_id VARCHAR2(36 CHAR),
	idempotency_key VARCHAR2(100 CHAR),
	request_key_hash VARCHAR2(64 CHAR),
	request_digest VARCHAR2(64 CHAR),
	memory_kind VARCHAR2(20 CHAR) DEFAULT 'DOCUMENT' NOT NULL,
	scope VARCHAR2(108 CHAR) DEFAULT 'global' NOT NULL,
	lifecycle_status VARCHAR2(16 CHAR) DEFAULT 'ACTIVE' NOT NULL,
	superseded_by_id VARCHAR2(36 CHAR),
	retired_at DATE,
	created_at DATE NOT NULL,
	updated_at DATE,
	PRIMARY KEY (id),
	UNIQUE (owner_id, id),
	CONSTRAINT vk_item_request_uq UNIQUE (request_key_hash),
	CONSTRAINT vk_item_superseded_fk FOREIGN KEY(owner_id, superseded_by_id) REFERENCES vk_item (owner_id, id)
);

CREATE INDEX ix_vk_item_scope ON vk_item (scope);

CREATE INDEX ix_vk_item_owner_id ON vk_item (owner_id);

CREATE TABLE vk_g_entity (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	scope VARCHAR2(108 CHAR) NOT NULL,
	identity_hash VARCHAR2(64 CHAR) NOT NULL,
	identity_key VARCHAR2(200 CHAR) NOT NULL,
	label VARCHAR2(200 CHAR) NOT NULL,
	kind VARCHAR2(40 CHAR) NOT NULL,
	aliases_json CLOB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (owner_id, id),
	UNIQUE (identity_hash)
);

CREATE INDEX ix_vk_g_entity_scope ON vk_g_entity (scope);

CREATE INDEX ix_vk_g_entity_owner_id ON vk_g_entity (owner_id);

CREATE TABLE vk_g_claim (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	scope VARCHAR2(108 CHAR) NOT NULL,
	signature VARCHAR2(64 CHAR) NOT NULL,
	current_version_id VARCHAR2(36 CHAR),
	PRIMARY KEY (id),
	UNIQUE (owner_id, id),
	UNIQUE (signature)
);

CREATE INDEX ix_vk_g_claim_scope ON vk_g_claim (scope);

CREATE INDEX ix_vk_g_claim_owner_id ON vk_g_claim (owner_id);

CREATE TABLE vk_index (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	scope VARCHAR2(108 CHAR) NOT NULL,
	key VARCHAR2(120 CHAR) NOT NULL,
	key_hash VARCHAR2(64 CHAR) NOT NULL,
	title VARCHAR2(200 CHAR) NOT NULL,
	summary VARCHAR2(1000 CHAR) NOT NULL,
	body CLOB,
	version INTEGER NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (owner_id, id),
	UNIQUE (key_hash)
);

CREATE INDEX ix_vk_index_owner_id ON vk_index (owner_id);

CREATE INDEX ix_vk_index_scope ON vk_index (scope);

CREATE TABLE vk_nav_snapshot (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	payload_json CLOB NOT NULL,
	native_stored INTEGER NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_vk_nav_snapshot_owner_id ON vk_nav_snapshot (owner_id);

CREATE TABLE vk_change_context (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	transaction_id VARCHAR2(100 CHAR),
	operation VARCHAR2(80 CHAR) NOT NULL,
	request_id VARCHAR2(36 CHAR) NOT NULL,
	actor_subject VARCHAR2(500 CHAR),
	actor_issuer VARCHAR2(500 CHAR),
	machine_id VARCHAR2(100 CHAR),
	edit_origin VARCHAR2(16 CHAR),
	reason VARCHAR2(500 CHAR),
	source VARCHAR2(16 CHAR) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_vk_change_context_transaction_id ON vk_change_context (transaction_id);

CREATE TABLE vk_change_event (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	context_id VARCHAR2(36 CHAR),
	table_name VARCHAR2(40 CHAR) NOT NULL,
	target_id VARCHAR2(36 CHAR) NOT NULL,
	action VARCHAR2(10 CHAR) NOT NULL,
	before_json CLOB,
	after_json CLOB,
	db_user VARCHAR2(128 CHAR),
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_vk_change_event_created_at ON vk_change_event (created_at);

CREATE INDEX ix_vk_change_event_owner_id ON vk_change_event (owner_id);

CREATE INDEX ix_vk_change_event_target_id ON vk_change_event (target_id);

CREATE TABLE vk_change_review (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	event_id VARCHAR2(36 CHAR) NOT NULL,
	target_type VARCHAR2(40 CHAR) NOT NULL,
	target_id VARCHAR2(36 CHAR) NOT NULL,
	reason VARCHAR2(80 CHAR) NOT NULL,
	status VARCHAR2(16 CHAR) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	resolved_at TIMESTAMP WITH TIME ZONE,
	resolution_note VARCHAR2(1000 CHAR),
	resolved_by VARCHAR2(500 CHAR),
	PRIMARY KEY (id),
	CONSTRAINT vk_change_review_uq UNIQUE (event_id, target_type, target_id, reason)
);

CREATE INDEX ix_vk_change_review_status ON vk_change_review (status);

CREATE INDEX ix_vk_change_review_owner_id ON vk_change_review (owner_id);

CREATE TABLE vk_g_extract (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	item_id VARCHAR2(36 CHAR) NOT NULL,
	revision_id VARCHAR2(36 CHAR) NOT NULL,
	run_key VARCHAR2(64 CHAR) NOT NULL,
	schema_version VARCHAR2(40 CHAR) NOT NULL,
	model VARCHAR2(200 CHAR) NOT NULL,
	status VARCHAR2(20 CHAR) NOT NULL,
	attempts INTEGER NOT NULL,
	retry_limit INTEGER NOT NULL,
	force_extract INTEGER NOT NULL,
	lease_token VARCHAR2(36 CHAR),
	available_at TIMESTAMP WITH TIME ZONE NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	route_json CLOB,
	error_code VARCHAR2(80 CHAR),
	PRIMARY KEY (id),
	UNIQUE (run_key)
);

CREATE INDEX ix_vk_g_extract_owner_id ON vk_g_extract (owner_id);

CREATE INDEX ix_vk_g_extract_status ON vk_g_extract (status);

CREATE TABLE vk_g_proposal (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	run_id VARCHAR2(36 CHAR) NOT NULL,
	item_id VARCHAR2(36 CHAR) NOT NULL,
	revision_id VARCHAR2(36 CHAR) NOT NULL,
	scope VARCHAR2(108 CHAR) NOT NULL,
	candidate_key VARCHAR2(64 CHAR) NOT NULL,
	payload_json CLOB NOT NULL,
	status VARCHAR2(20 CHAR) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	reviewed_at TIMESTAMP WITH TIME ZONE,
	reviewed_by VARCHAR2(500 CHAR),
	review_note VARCHAR2(1000 CHAR),
	resolution_json CLOB,
	assertion_id VARCHAR2(36 CHAR),
	version_id VARCHAR2(36 CHAR),
	PRIMARY KEY (id),
	UNIQUE (candidate_key)
);

CREATE INDEX ix_vk_g_proposal_owner_id ON vk_g_proposal (owner_id);

CREATE INDEX ix_vk_g_proposal_status ON vk_g_proposal (status);

CREATE INDEX ix_vk_g_proposal_run_id ON vk_g_proposal (run_id);

CREATE TABLE vk_g_review (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	item_id VARCHAR2(36 CHAR) NOT NULL,
	revision_id VARCHAR2(36 CHAR) NOT NULL,
	version INTEGER NOT NULL,
	status VARCHAR2(20 CHAR) NOT NULL,
	outcome VARCHAR2(20 CHAR),
	note VARCHAR2(1000 CHAR) NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (revision_id)
);

CREATE INDEX ix_vk_g_review_owner_id ON vk_g_review (owner_id);

CREATE TABLE vk_g_identity (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	scope VARCHAR2(108 CHAR) NOT NULL,
	binding_key VARCHAR2(64 CHAR) NOT NULL,
	entity_id VARCHAR2(36 CHAR) NOT NULL,
	kind VARCHAR2(16 CHAR) NOT NULL,
	namespace VARCHAR2(40 CHAR) NOT NULL,
	value VARCHAR2(500 CHAR) NOT NULL,
	version INTEGER NOT NULL,
	status VARCHAR2(16 CHAR) NOT NULL,
	item_id VARCHAR2(36 CHAR) NOT NULL,
	revision_id VARCHAR2(36 CHAR) NOT NULL,
	quote CLOB NOT NULL,
	note VARCHAR2(1000 CHAR) NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (binding_key)
);

CREATE INDEX ix_vk_g_identity_owner_id ON vk_g_identity (owner_id);

CREATE TABLE vk_g_operation (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	target_id VARCHAR2(36 CHAR) NOT NULL,
	kind VARCHAR2(16 CHAR) NOT NULL,
	version INTEGER NOT NULL,
	actor VARCHAR2(500 CHAR) NOT NULL,
	snapshot_json CLOB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT vk_g_op_version_uq UNIQUE (target_id, version)
);

CREATE INDEX ix_vk_g_operation_target_id ON vk_g_operation (target_id);

CREATE INDEX ix_vk_g_operation_owner_id ON vk_g_operation (owner_id);

CREATE TABLE vk_principle_bundle (
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	version INTEGER NOT NULL,
	rules_json CLOB NOT NULL,
	updated_at DATE NOT NULL,
	PRIMARY KEY (owner_id)
);

CREATE TABLE vk_principle_revision (
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	version INTEGER NOT NULL,
	rules_json CLOB NOT NULL,
	change_note VARCHAR2(500 CHAR) NOT NULL,
	actor_id VARCHAR2(64 CHAR) NOT NULL,
	created_at DATE NOT NULL,
	PRIMARY KEY (owner_id, version)
);

CREATE TABLE vk_revision (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	item_id VARCHAR2(36 CHAR) NOT NULL,
	revision_no INTEGER DEFAULT '1' NOT NULL,
	change_note VARCHAR2(500 CHAR),
	edit_origin VARCHAR2(16 CHAR),
	origin_machine_id VARCHAR2(100 CHAR),
	origin_machine_label VARCHAR2(120 CHAR),
	sources_json CLOB,
	content_text CLOB,
	summary_text CLOB,
	summary_kind VARCHAR2(16 CHAR),
	source_type VARCHAR2(10 CHAR) NOT NULL,
	source_url VARCHAR2(2000 CHAR),
	filename VARCHAR2(300 CHAR),
	mime_type VARCHAR2(100 CHAR) NOT NULL,
	original_data BLOB,
	created_at DATE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (owner_id, id),
	CONSTRAINT vk_revision_no_uq UNIQUE (item_id, revision_no),
	FOREIGN KEY(owner_id, item_id) REFERENCES vk_item (owner_id, id)
);

CREATE INDEX ix_vk_revision_item_id ON vk_revision (item_id);

CREATE TABLE vk_g_version (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	claim_id VARCHAR2(36 CHAR) NOT NULL,
	scope VARCHAR2(108 CHAR) NOT NULL,
	subject_id VARCHAR2(36 CHAR) NOT NULL,
	object_id VARCHAR2(36 CHAR),
	predicate VARCHAR2(40 CHAR) NOT NULL,
	temporal_kind VARCHAR2(16 CHAR) NOT NULL,
	valid_from TIMESTAMP WITH TIME ZONE,
	valid_to TIMESTAMP WITH TIME ZONE,
	recorded_from TIMESTAMP WITH TIME ZONE NOT NULL,
	recorded_to TIMESTAMP WITH TIME ZONE,
	status VARCHAR2(16 CHAR) NOT NULL,
	payload_json CLOB NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (owner_id, id),
	FOREIGN KEY(owner_id, claim_id) REFERENCES vk_g_claim (owner_id, id),
	FOREIGN KEY(owner_id, subject_id) REFERENCES vk_g_entity (owner_id, id),
	FOREIGN KEY(owner_id, object_id) REFERENCES vk_g_entity (owner_id, id)
);

CREATE INDEX ix_vk_g_version_subject_id ON vk_g_version (subject_id);

CREATE INDEX ix_vk_g_version_owner_id ON vk_g_version (owner_id);

CREATE INDEX ix_vk_g_version_scope ON vk_g_version (scope);

CREATE INDEX ix_vk_g_version_object_id ON vk_g_version (object_id);

CREATE INDEX ix_vk_g_version_recorded_from ON vk_g_version (recorded_from);

CREATE INDEX ix_vk_g_version_claim_id ON vk_g_version (claim_id);

CREATE TABLE vk_index_entry (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	index_id VARCHAR2(36 CHAR) NOT NULL,
	item_id VARCHAR2(36 CHAR) NOT NULL,
	section VARCHAR2(120 CHAR) NOT NULL,
	position INTEGER NOT NULL,
	note VARCHAR2(300 CHAR),
	PRIMARY KEY (id),
	UNIQUE (index_id, item_id),
	FOREIGN KEY(owner_id, index_id) REFERENCES vk_index (owner_id, id),
	FOREIGN KEY(owner_id, item_id) REFERENCES vk_item (owner_id, id)
);

CREATE INDEX ix_vk_index_entry_item_id ON vk_index_entry (item_id);

CREATE INDEX ix_vk_index_entry_owner_id ON vk_index_entry (owner_id);

CREATE INDEX ix_vk_index_entry_index_id ON vk_index_entry (index_id);

CREATE TABLE vk_index_change (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	index_id VARCHAR2(36 CHAR) NOT NULL,
	version INTEGER NOT NULL,
	payload_json CLOB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (index_id, version),
	FOREIGN KEY(owner_id, index_id) REFERENCES vk_index (owner_id, id)
);

CREATE INDEX ix_vk_index_change_index_id ON vk_index_change (index_id);

CREATE TABLE vk_change_outbox (
	event_id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	status VARCHAR2(16 CHAR) NOT NULL,
	attempts INTEGER NOT NULL,
	retry_limit INTEGER NOT NULL,
	available_at TIMESTAMP WITH TIME ZONE NOT NULL,
	processed_at TIMESTAMP WITH TIME ZONE,
	error_code VARCHAR2(80 CHAR),
	PRIMARY KEY (event_id),
	FOREIGN KEY(event_id) REFERENCES vk_change_event (id)
);

CREATE INDEX ix_vk_change_outbox_status ON vk_change_outbox (status);

CREATE INDEX ix_vk_change_outbox_owner_id ON vk_change_outbox (owner_id);

CREATE TABLE vk_event (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	item_id VARCHAR2(36 CHAR) NOT NULL,
	event_type VARCHAR2(20 CHAR) NOT NULL,
	revision_id VARCHAR2(36 CHAR),
	related_item_id VARCHAR2(36 CHAR),
	reason VARCHAR2(500 CHAR),
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT vk_event_item_fk FOREIGN KEY(owner_id, item_id) REFERENCES vk_item (owner_id, id),
	CONSTRAINT vk_event_revision_fk FOREIGN KEY(owner_id, revision_id) REFERENCES vk_revision (owner_id, id),
	CONSTRAINT vk_event_related_fk FOREIGN KEY(owner_id, related_item_id) REFERENCES vk_item (owner_id, id)
);

CREATE INDEX ix_vk_event_item_id ON vk_event (item_id);

CREATE TABLE vk_job (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	revision_id VARCHAR2(36 CHAR) NOT NULL,
	status VARCHAR2(16 CHAR) NOT NULL,
	stage VARCHAR2(20 CHAR) NOT NULL,
	error_code VARCHAR2(80 CHAR),
	created_at DATE NOT NULL,
	started_at DATE,
	PRIMARY KEY (id),
	FOREIGN KEY(owner_id, revision_id) REFERENCES vk_revision (owner_id, id),
	UNIQUE (revision_id)
);

CREATE INDEX ix_vk_job_status ON vk_job (status);

CREATE TABLE vk_chunk (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	revision_id VARCHAR2(36 CHAR) NOT NULL,
	source_part VARCHAR2(16 CHAR),
	chunk_no INTEGER NOT NULL,
	text CLOB NOT NULL,
	page_no INTEGER NOT NULL,
	char_start INTEGER NOT NULL,
	char_end INTEGER NOT NULL,
	profile_id VARCHAR2(64 CHAR) NOT NULL,
	embedding VECTOR(1024,FLOAT32,*) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (revision_id, chunk_no),
	FOREIGN KEY(owner_id, revision_id) REFERENCES vk_revision (owner_id, id)
);

CREATE INDEX ix_vk_chunk_revision_id ON vk_chunk (revision_id);

CREATE INDEX ix_vk_chunk_profile_id ON vk_chunk (profile_id);

CREATE INDEX ix_vk_chunk_owner_id ON vk_chunk (owner_id);

CREATE TABLE vk_workflow (
	revision_id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	payload_json CLOB NOT NULL,
	payload_hash VARCHAR2(64 CHAR) NOT NULL,
	created_at DATE NOT NULL,
	PRIMARY KEY (revision_id),
	FOREIGN KEY(owner_id, revision_id) REFERENCES vk_revision (owner_id, id)
);

CREATE TABLE vk_g_evidence (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	version_id VARCHAR2(36 CHAR) NOT NULL,
	knowledge_id VARCHAR2(36 CHAR) NOT NULL,
	revision_id VARCHAR2(36 CHAR) NOT NULL,
	quote CLOB NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(owner_id, version_id) REFERENCES vk_g_version (owner_id, id),
	FOREIGN KEY(owner_id, revision_id) REFERENCES vk_revision (owner_id, id),
	FOREIGN KEY(owner_id, knowledge_id) REFERENCES vk_item (owner_id, id)
);

CREATE INDEX ix_vk_g_evidence_version_id ON vk_g_evidence (version_id);

CREATE INDEX ix_vk_g_evidence_revision_id ON vk_g_evidence (revision_id);

CREATE INDEX ix_vk_g_evidence_knowledge_id ON vk_g_evidence (knowledge_id);

CREATE TABLE vk_memory_evidence (
	id VARCHAR2(64 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	memory_id VARCHAR2(128 CHAR) NOT NULL,
	knowledge_id VARCHAR2(36 CHAR) NOT NULL,
	revision_id VARCHAR2(36 CHAR) NOT NULL,
	quote CLOB NOT NULL,
	reason VARCHAR2(1000 CHAR) NOT NULL,
	created_at DATE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(owner_id, knowledge_id) REFERENCES vk_item (owner_id, id),
	FOREIGN KEY(owner_id, revision_id) REFERENCES vk_revision (owner_id, id)
);

CREATE INDEX ix_vk_memory_evidence_owner_id ON vk_memory_evidence (owner_id);

CREATE INDEX ix_vk_memory_evidence_memory_id ON vk_memory_evidence (memory_id);

CREATE INDEX ix_vk_memory_evidence_knowledge_id ON vk_memory_evidence (knowledge_id);

ALTER TABLE vk_item ADD CONSTRAINT vk_item_active_fk FOREIGN KEY(owner_id, active_revision_id) REFERENCES vk_revision (owner_id, id);

CREATE OR REPLACE TRIGGER vk_audit_0
AFTER INSERT OR UPDATE OR DELETE ON vk_item FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.id <> :NEW.id) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.id; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.id;
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT JSON_OBJECT('id' VALUE :OLD.id, 'owner_id' VALUE :OLD.owner_id, 'title' VALUE :OLD.title, 'knowledge_type' VALUE :OLD.knowledge_type, 'category' VALUE :OLD.category, 'tags_json' VALUE :OLD.tags_json, 'memory_kind' VALUE :OLD.memory_kind, 'scope' VALUE :OLD.scope, 'active_revision_id' VALUE :OLD.active_revision_id, 'lifecycle_status' VALUE :OLD.lifecycle_status, 'superseded_by_id' VALUE :OLD.superseded_by_id, 'retired_at' VALUE :OLD.retired_at RETURNING CLOB) INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT JSON_OBJECT('id' VALUE :NEW.id, 'owner_id' VALUE :NEW.owner_id, 'title' VALUE :NEW.title, 'knowledge_type' VALUE :NEW.knowledge_type, 'category' VALUE :NEW.category, 'tags_json' VALUE :NEW.tags_json, 'memory_kind' VALUE :NEW.memory_kind, 'scope' VALUE :NEW.scope, 'active_revision_id' VALUE :NEW.active_revision_id, 'lifecycle_status' VALUE :NEW.lifecycle_status, 'superseded_by_id' VALUE :NEW.superseded_by_id, 'retired_at' VALUE :NEW.retired_at RETURNING CLOB) INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'vk_item',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;;

CREATE OR REPLACE TRIGGER vk_audit_1
AFTER INSERT OR UPDATE OR DELETE ON vk_revision FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.id <> :NEW.id) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.id; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.id;
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT JSON_OBJECT('id' VALUE :OLD.id, 'owner_id' VALUE :OLD.owner_id, 'item_id' VALUE :OLD.item_id, 'revision_no' VALUE :OLD.revision_no, 'change_note' VALUE :OLD.change_note, 'edit_origin' VALUE :OLD.edit_origin, 'origin_machine_id' VALUE :OLD.origin_machine_id, 'origin_machine_label' VALUE :OLD.origin_machine_label, 'sources_json' VALUE :OLD.sources_json, 'content_text' VALUE :OLD.content_text, 'summary_text' VALUE :OLD.summary_text, 'summary_kind' VALUE :OLD.summary_kind, 'source_type' VALUE :OLD.source_type, 'source_url' VALUE :OLD.source_url, 'filename' VALUE :OLD.filename, 'mime_type' VALUE :OLD.mime_type, 'original_bytes' VALUE DBMS_LOB.GETLENGTH(:OLD.original_data) RETURNING CLOB) INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT JSON_OBJECT('id' VALUE :NEW.id, 'owner_id' VALUE :NEW.owner_id, 'item_id' VALUE :NEW.item_id, 'revision_no' VALUE :NEW.revision_no, 'change_note' VALUE :NEW.change_note, 'edit_origin' VALUE :NEW.edit_origin, 'origin_machine_id' VALUE :NEW.origin_machine_id, 'origin_machine_label' VALUE :NEW.origin_machine_label, 'sources_json' VALUE :NEW.sources_json, 'content_text' VALUE :NEW.content_text, 'summary_text' VALUE :NEW.summary_text, 'summary_kind' VALUE :NEW.summary_kind, 'source_type' VALUE :NEW.source_type, 'source_url' VALUE :NEW.source_url, 'filename' VALUE :NEW.filename, 'mime_type' VALUE :NEW.mime_type, 'original_bytes' VALUE DBMS_LOB.GETLENGTH(:NEW.original_data) RETURNING CLOB) INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'vk_revision',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;;

CREATE OR REPLACE TRIGGER vk_audit_2
AFTER INSERT OR UPDATE OR DELETE ON vk_index FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.id <> :NEW.id) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.id; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.id;
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT JSON_OBJECT('id' VALUE :OLD.id, 'owner_id' VALUE :OLD.owner_id, 'scope' VALUE :OLD.scope, 'key' VALUE :OLD.key, 'title' VALUE :OLD.title, 'summary' VALUE :OLD.summary, 'body' VALUE :OLD.body, 'version' VALUE :OLD.version RETURNING CLOB) INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT JSON_OBJECT('id' VALUE :NEW.id, 'owner_id' VALUE :NEW.owner_id, 'scope' VALUE :NEW.scope, 'key' VALUE :NEW.key, 'title' VALUE :NEW.title, 'summary' VALUE :NEW.summary, 'body' VALUE :NEW.body, 'version' VALUE :NEW.version RETURNING CLOB) INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'vk_index',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;;

CREATE OR REPLACE TRIGGER vk_audit_3
AFTER INSERT OR UPDATE OR DELETE ON vk_index_entry FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.id <> :NEW.id) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.id; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.id;
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT JSON_OBJECT('id' VALUE :OLD.id, 'owner_id' VALUE :OLD.owner_id, 'index_id' VALUE :OLD.index_id, 'item_id' VALUE :OLD.item_id, 'section' VALUE :OLD.section, 'position' VALUE :OLD.position, 'note' VALUE :OLD.note RETURNING CLOB) INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT JSON_OBJECT('id' VALUE :NEW.id, 'owner_id' VALUE :NEW.owner_id, 'index_id' VALUE :NEW.index_id, 'item_id' VALUE :NEW.item_id, 'section' VALUE :NEW.section, 'position' VALUE :NEW.position, 'note' VALUE :NEW.note RETURNING CLOB) INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'vk_index_entry',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;;

CREATE OR REPLACE TRIGGER vk_audit_4
AFTER INSERT OR UPDATE OR DELETE ON vk_g_entity FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.id <> :NEW.id) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.id; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.id;
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT JSON_OBJECT('id' VALUE :OLD.id, 'owner_id' VALUE :OLD.owner_id, 'scope' VALUE :OLD.scope, 'identity_key' VALUE :OLD.identity_key, 'label' VALUE :OLD.label, 'kind' VALUE :OLD.kind, 'aliases_json' VALUE :OLD.aliases_json RETURNING CLOB) INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT JSON_OBJECT('id' VALUE :NEW.id, 'owner_id' VALUE :NEW.owner_id, 'scope' VALUE :NEW.scope, 'identity_key' VALUE :NEW.identity_key, 'label' VALUE :NEW.label, 'kind' VALUE :NEW.kind, 'aliases_json' VALUE :NEW.aliases_json RETURNING CLOB) INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'vk_g_entity',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;;

CREATE OR REPLACE TRIGGER vk_audit_5
AFTER INSERT OR UPDATE OR DELETE ON vk_g_claim FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.id <> :NEW.id) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.id; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.id;
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT JSON_OBJECT('id' VALUE :OLD.id, 'owner_id' VALUE :OLD.owner_id, 'scope' VALUE :OLD.scope, 'current_version_id' VALUE :OLD.current_version_id, 'signature' VALUE :OLD.signature RETURNING CLOB) INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT JSON_OBJECT('id' VALUE :NEW.id, 'owner_id' VALUE :NEW.owner_id, 'scope' VALUE :NEW.scope, 'current_version_id' VALUE :NEW.current_version_id, 'signature' VALUE :NEW.signature RETURNING CLOB) INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'vk_g_claim',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;;

CREATE OR REPLACE TRIGGER vk_audit_6
AFTER INSERT OR UPDATE OR DELETE ON vk_g_version FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.id <> :NEW.id) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.id; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.id;
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT JSON_OBJECT('id' VALUE :OLD.id, 'owner_id' VALUE :OLD.owner_id, 'claim_id' VALUE :OLD.claim_id, 'scope' VALUE :OLD.scope, 'subject_id' VALUE :OLD.subject_id, 'object_id' VALUE :OLD.object_id, 'predicate' VALUE :OLD.predicate, 'temporal_kind' VALUE :OLD.temporal_kind, 'valid_from' VALUE :OLD.valid_from, 'valid_to' VALUE :OLD.valid_to, 'recorded_from' VALUE :OLD.recorded_from, 'recorded_to' VALUE :OLD.recorded_to, 'status' VALUE :OLD.status, 'payload_json' VALUE :OLD.payload_json RETURNING CLOB) INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT JSON_OBJECT('id' VALUE :NEW.id, 'owner_id' VALUE :NEW.owner_id, 'claim_id' VALUE :NEW.claim_id, 'scope' VALUE :NEW.scope, 'subject_id' VALUE :NEW.subject_id, 'object_id' VALUE :NEW.object_id, 'predicate' VALUE :NEW.predicate, 'temporal_kind' VALUE :NEW.temporal_kind, 'valid_from' VALUE :NEW.valid_from, 'valid_to' VALUE :NEW.valid_to, 'recorded_from' VALUE :NEW.recorded_from, 'recorded_to' VALUE :NEW.recorded_to, 'status' VALUE :NEW.status, 'payload_json' VALUE :NEW.payload_json RETURNING CLOB) INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'vk_g_version',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;;

CREATE OR REPLACE TRIGGER vk_audit_7
AFTER INSERT OR UPDATE OR DELETE ON vk_g_evidence FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.id <> :NEW.id) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.id; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.id;
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT JSON_OBJECT('id' VALUE :OLD.id, 'owner_id' VALUE :OLD.owner_id, 'version_id' VALUE :OLD.version_id, 'knowledge_id' VALUE :OLD.knowledge_id, 'revision_id' VALUE :OLD.revision_id, 'quote' VALUE :OLD.quote RETURNING CLOB) INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT JSON_OBJECT('id' VALUE :NEW.id, 'owner_id' VALUE :NEW.owner_id, 'version_id' VALUE :NEW.version_id, 'knowledge_id' VALUE :NEW.knowledge_id, 'revision_id' VALUE :NEW.revision_id, 'quote' VALUE :NEW.quote RETURNING CLOB) INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'vk_g_evidence',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;;

CREATE OR REPLACE TRIGGER vk_audit_8
AFTER INSERT OR UPDATE OR DELETE ON vk_workflow FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.revision_id <> :NEW.revision_id) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.revision_id; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.revision_id;
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT JSON_OBJECT('revision_id' VALUE :OLD.revision_id, 'owner_id' VALUE :OLD.owner_id, 'payload_json' VALUE :OLD.payload_json, 'payload_hash' VALUE :OLD.payload_hash RETURNING CLOB) INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT JSON_OBJECT('revision_id' VALUE :NEW.revision_id, 'owner_id' VALUE :NEW.owner_id, 'payload_json' VALUE :NEW.payload_json, 'payload_hash' VALUE :NEW.payload_hash RETURNING CLOB) INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'vk_workflow',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;;

CREATE OR REPLACE TRIGGER vk_audit_append_only BEFORE UPDATE OR DELETE ON vk_change_event
BEGIN RAISE_APPLICATION_ERROR(-20082,'AUDIT_APPEND_ONLY'); END;;

CREATE OR REPLACE TRIGGER vk_audit_9
AFTER INSERT OR UPDATE OR DELETE ON vk_g_extract FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.id <> :NEW.id) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.id; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.id;
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT JSON_OBJECT('id' VALUE :OLD.id, 'owner_id' VALUE :OLD.owner_id, 'item_id' VALUE :OLD.item_id, 'revision_id' VALUE :OLD.revision_id, 'run_key' VALUE :OLD.run_key, 'schema_version' VALUE :OLD.schema_version, 'model' VALUE :OLD.model, 'status' VALUE :OLD.status, 'attempts' VALUE :OLD.attempts, 'retry_limit' VALUE :OLD.retry_limit, 'force_extract' VALUE :OLD.force_extract, 'available_at' VALUE :OLD.available_at, 'created_at' VALUE :OLD.created_at, 'updated_at' VALUE :OLD.updated_at, 'route_json' VALUE :OLD.route_json, 'error_code' VALUE :OLD.error_code RETURNING CLOB) INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT JSON_OBJECT('id' VALUE :NEW.id, 'owner_id' VALUE :NEW.owner_id, 'item_id' VALUE :NEW.item_id, 'revision_id' VALUE :NEW.revision_id, 'run_key' VALUE :NEW.run_key, 'schema_version' VALUE :NEW.schema_version, 'model' VALUE :NEW.model, 'status' VALUE :NEW.status, 'attempts' VALUE :NEW.attempts, 'retry_limit' VALUE :NEW.retry_limit, 'force_extract' VALUE :NEW.force_extract, 'available_at' VALUE :NEW.available_at, 'created_at' VALUE :NEW.created_at, 'updated_at' VALUE :NEW.updated_at, 'route_json' VALUE :NEW.route_json, 'error_code' VALUE :NEW.error_code RETURNING CLOB) INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'vk_g_extract',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;;

CREATE OR REPLACE TRIGGER vk_audit_10
AFTER INSERT OR UPDATE OR DELETE ON vk_g_proposal FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.id <> :NEW.id) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.id; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.id;
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT JSON_OBJECT('id' VALUE :OLD.id, 'owner_id' VALUE :OLD.owner_id, 'run_id' VALUE :OLD.run_id, 'item_id' VALUE :OLD.item_id, 'revision_id' VALUE :OLD.revision_id, 'scope' VALUE :OLD.scope, 'candidate_key' VALUE :OLD.candidate_key, 'payload_json' VALUE :OLD.payload_json, 'status' VALUE :OLD.status, 'created_at' VALUE :OLD.created_at, 'reviewed_at' VALUE :OLD.reviewed_at, 'reviewed_by' VALUE :OLD.reviewed_by, 'review_note' VALUE :OLD.review_note, 'resolution_json' VALUE :OLD.resolution_json, 'assertion_id' VALUE :OLD.assertion_id, 'version_id' VALUE :OLD.version_id RETURNING CLOB) INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT JSON_OBJECT('id' VALUE :NEW.id, 'owner_id' VALUE :NEW.owner_id, 'run_id' VALUE :NEW.run_id, 'item_id' VALUE :NEW.item_id, 'revision_id' VALUE :NEW.revision_id, 'scope' VALUE :NEW.scope, 'candidate_key' VALUE :NEW.candidate_key, 'payload_json' VALUE :NEW.payload_json, 'status' VALUE :NEW.status, 'created_at' VALUE :NEW.created_at, 'reviewed_at' VALUE :NEW.reviewed_at, 'reviewed_by' VALUE :NEW.reviewed_by, 'review_note' VALUE :NEW.review_note, 'resolution_json' VALUE :NEW.resolution_json, 'assertion_id' VALUE :NEW.assertion_id, 'version_id' VALUE :NEW.version_id RETURNING CLOB) INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'vk_g_proposal',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;;

CREATE OR REPLACE TRIGGER vk_audit_11
AFTER INSERT OR UPDATE OR DELETE ON vk_g_review FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.id <> :NEW.id) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.id; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.id;
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT JSON_OBJECT('id' VALUE :OLD.id, 'owner_id' VALUE :OLD.owner_id, 'item_id' VALUE :OLD.item_id, 'revision_id' VALUE :OLD.revision_id, 'version' VALUE :OLD.version, 'status' VALUE :OLD.status, 'outcome' VALUE :OLD.outcome, 'note' VALUE :OLD.note, 'updated_at' VALUE :OLD.updated_at RETURNING CLOB) INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT JSON_OBJECT('id' VALUE :NEW.id, 'owner_id' VALUE :NEW.owner_id, 'item_id' VALUE :NEW.item_id, 'revision_id' VALUE :NEW.revision_id, 'version' VALUE :NEW.version, 'status' VALUE :NEW.status, 'outcome' VALUE :NEW.outcome, 'note' VALUE :NEW.note, 'updated_at' VALUE :NEW.updated_at RETURNING CLOB) INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'vk_g_review',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;;

CREATE OR REPLACE TRIGGER vk_audit_12
AFTER INSERT OR UPDATE OR DELETE ON vk_g_identity FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.id <> :NEW.id) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.id; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.id;
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT JSON_OBJECT('id' VALUE :OLD.id, 'owner_id' VALUE :OLD.owner_id, 'scope' VALUE :OLD.scope, 'binding_key' VALUE :OLD.binding_key, 'entity_id' VALUE :OLD.entity_id, 'kind' VALUE :OLD.kind, 'namespace' VALUE :OLD.namespace, 'value' VALUE :OLD.value, 'version' VALUE :OLD.version, 'status' VALUE :OLD.status, 'item_id' VALUE :OLD.item_id, 'revision_id' VALUE :OLD.revision_id, 'quote' VALUE :OLD.quote, 'note' VALUE :OLD.note, 'updated_at' VALUE :OLD.updated_at RETURNING CLOB) INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT JSON_OBJECT('id' VALUE :NEW.id, 'owner_id' VALUE :NEW.owner_id, 'scope' VALUE :NEW.scope, 'binding_key' VALUE :NEW.binding_key, 'entity_id' VALUE :NEW.entity_id, 'kind' VALUE :NEW.kind, 'namespace' VALUE :NEW.namespace, 'value' VALUE :NEW.value, 'version' VALUE :NEW.version, 'status' VALUE :NEW.status, 'item_id' VALUE :NEW.item_id, 'revision_id' VALUE :NEW.revision_id, 'quote' VALUE :NEW.quote, 'note' VALUE :NEW.note, 'updated_at' VALUE :NEW.updated_at RETURNING CLOB) INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'vk_g_identity',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;;

CREATE OR REPLACE TRIGGER vk_audit_13
AFTER INSERT OR UPDATE OR DELETE ON vk_g_operation FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.id <> :NEW.id) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.id; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.id;
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT JSON_OBJECT('id' VALUE :OLD.id, 'owner_id' VALUE :OLD.owner_id, 'target_id' VALUE :OLD.target_id, 'kind' VALUE :OLD.kind, 'version' VALUE :OLD.version, 'actor' VALUE :OLD.actor, 'snapshot_json' VALUE :OLD.snapshot_json, 'created_at' VALUE :OLD.created_at RETURNING CLOB) INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT JSON_OBJECT('id' VALUE :NEW.id, 'owner_id' VALUE :NEW.owner_id, 'target_id' VALUE :NEW.target_id, 'kind' VALUE :NEW.kind, 'version' VALUE :NEW.version, 'actor' VALUE :NEW.actor, 'snapshot_json' VALUE :NEW.snapshot_json, 'created_at' VALUE :NEW.created_at RETURNING CLOB) INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'vk_g_operation',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;;

CREATE OR REPLACE TRIGGER vk_audit_op_append_only BEFORE UPDATE OR DELETE ON vk_g_operation
BEGIN RAISE_APPLICATION_ERROR(-20082,'AUDIT_APPEND_ONLY'); END;;

CREATE TABLE vk_memory_lock (
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	PRIMARY KEY (owner_id)
);
