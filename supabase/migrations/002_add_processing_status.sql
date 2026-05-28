-- Add 'processing' to workflow_status for background job polling.

ALTER DOMAIN workflow_status DROP CONSTRAINT workflow_status_check;
ALTER DOMAIN workflow_status ADD CHECK (VALUE IN (
    'pending',
    'processing',
    'in_review',
    'needs_revision',
    'approved',
    'error',
    'completed'
));
