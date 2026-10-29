-- Reference table/index DDL. Install with Alembic; vk0008 also installs audit triggers.

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

CREATE INDEX ix_vk_change_review_owner_id ON vk_change_review (owner_id);

CREATE INDEX ix_vk_change_review_status ON vk_change_review (status);

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

CREATE INDEX ix_vk_g_claim_owner_id ON vk_g_claim (owner_id);

CREATE INDEX ix_vk_g_claim_scope ON vk_g_claim (scope);

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

CREATE INDEX ix_vk_g_entity_owner_id ON vk_g_entity (owner_id);

CREATE INDEX ix_vk_g_entity_scope ON vk_g_entity (scope);

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

CREATE INDEX ix_vk_g_proposal_run_id ON vk_g_proposal (run_id);

CREATE INDEX ix_vk_g_proposal_status ON vk_g_proposal (status);

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

CREATE INDEX ix_vk_item_owner_id ON vk_item (owner_id);

CREATE INDEX ix_vk_item_scope ON vk_item (scope);

CREATE TABLE vk_nav_snapshot (
	id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	payload_json CLOB NOT NULL,
	native_stored INTEGER NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_vk_nav_snapshot_owner_id ON vk_nav_snapshot (owner_id);

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

CREATE INDEX ix_vk_change_outbox_owner_id ON vk_change_outbox (owner_id);

CREATE INDEX ix_vk_change_outbox_status ON vk_change_outbox (status);

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

CREATE INDEX ix_vk_g_version_claim_id ON vk_g_version (claim_id);

CREATE INDEX ix_vk_g_version_object_id ON vk_g_version (object_id);

CREATE INDEX ix_vk_g_version_owner_id ON vk_g_version (owner_id);

CREATE INDEX ix_vk_g_version_recorded_from ON vk_g_version (recorded_from);

CREATE INDEX ix_vk_g_version_scope ON vk_g_version (scope);

CREATE INDEX ix_vk_g_version_subject_id ON vk_g_version (subject_id);

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

CREATE INDEX ix_vk_index_entry_index_id ON vk_index_entry (index_id);

CREATE INDEX ix_vk_index_entry_item_id ON vk_index_entry (item_id);

CREATE INDEX ix_vk_index_entry_owner_id ON vk_index_entry (owner_id);

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

CREATE INDEX ix_vk_chunk_owner_id ON vk_chunk (owner_id);

CREATE INDEX ix_vk_chunk_profile_id ON vk_chunk (profile_id);

CREATE INDEX ix_vk_chunk_revision_id ON vk_chunk (revision_id);

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

CREATE INDEX ix_vk_g_evidence_knowledge_id ON vk_g_evidence (knowledge_id);

CREATE INDEX ix_vk_g_evidence_revision_id ON vk_g_evidence (revision_id);

CREATE INDEX ix_vk_g_evidence_version_id ON vk_g_evidence (version_id);

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

CREATE TABLE vk_workflow (
	revision_id VARCHAR2(36 CHAR) NOT NULL,
	owner_id VARCHAR2(64 CHAR) NOT NULL,
	payload_json CLOB NOT NULL,
	payload_hash VARCHAR2(64 CHAR) NOT NULL,
	created_at DATE NOT NULL,
	PRIMARY KEY (revision_id),
	FOREIGN KEY(owner_id, revision_id) REFERENCES vk_revision (owner_id, id)
);

ALTER TABLE vk_item ADD CONSTRAINT vk_item_active_fk FOREIGN KEY(owner_id, active_revision_id) REFERENCES vk_revision (owner_id, id);
