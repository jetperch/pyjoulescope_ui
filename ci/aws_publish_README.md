<!--
# SPDX-FileCopyrightText: Copyright 2026 Jetperch LLC
# SPDX-License-Identifier: Apache-2.0
-->

# AWS configuration for the release publish step

The `publish` job in
[`.github/workflows/packaging.yml`](../.github/workflows/packaging.yml) runs
[`ci/publish.py`](publish.py) on a tag push to upload the installers to the
`download.joulescope.com` download server (an S3 bucket) and update
`joulescope_install/index_v2.json` + `index.html`.  Promotion to beta/stable is
done later by [`ci/release_update.py`](release_update.py).

Both scripts talk to S3 via `boto3` using **static access-key credentials**
provided as GitHub Actions secrets.  This document describes the one-time IAM
and secret setup.

- **Bucket:** `download-joulescope-com`
- **Prefix (only directory touched):** `joulescope_install/`

## Least-privilege policy

[`ci/aws_publish_policy.json`](aws_publish_policy.json) grants exactly what the
scripts need and nothing more:

- `s3:GetObject` + `s3:PutObject` on
  `arn:aws:s3:::download-joulescope-com/joulescope_install/*` — read the current
  index for the read-modify-write, and write the installers, `.sha256`
  sidecars, `index_v2.json`, and `index.html`.
- `s3:ListBucket` restricted (via an `s3:prefix` condition) to
  `joulescope_install/*` — so a missing `index_v2.json` returns a clean
  `404/NoSuchKey` (treated as "no index yet") instead of `403 AccessDenied`.

Deliberately **not** granted:

- No `s3:DeleteObject` — the pipeline never deletes, so it cannot remove
  installers or rewrite history destructively.
- No access to any other prefix in the bucket (IAM denies by default).
- No `s3:PutObjectAcl` — objects are made public by the **bucket policy**, not
  per-object ACLs, so uploads set no ACL.  If this bucket ever switches to
  ACL-based public read, add `s3:PutObjectAcl` here and an `ACL='public-read'`
  to the `put_object` calls in `_publish_common.S3Backend`.

## One-time setup

### 1. Create the IAM user and attach the policy

From a machine with admin AWS credentials, run from this `ci/` directory:

```bash
aws iam create-user --user-name gha-joulescope-ui-publisher

aws iam put-user-policy \
  --user-name gha-joulescope-ui-publisher \
  --policy-name joulescope-install-rw \
  --policy-document file://aws_publish_policy.json

aws iam create-access-key --user-name gha-joulescope-ui-publisher
```

The final command prints `AccessKeyId` and `SecretAccessKey`; the secret is
shown only once, so copy it now.

Find the bucket region for `AWS_DEFAULT_REGION`:

```bash
aws s3api get-bucket-location --bucket download-joulescope-com
# a null/None LocationConstraint means us-east-1
```

### 2. Add the GitHub Actions secrets

Run from the repository directory (or set them via
*Settings -> Secrets and variables -> Actions*):

```bash
gh secret set AWS_ACCESS_KEY_ID          --body "AKIA..."
gh secret set AWS_SECRET_ACCESS_KEY      --body "<secret>"
gh secret set AWS_DEFAULT_REGION         --body "us-east-1"   # from step 1
gh secret set JOULESCOPE_DOWNLOAD_BUCKET --body "download-joulescope-com"
```

These names match the `env:` block of the "Publish to download.joulescope.com"
step in the workflow.

### 3. Verify the scope

Confirm the credentials can write inside the prefix but not outside it:

```bash
export AWS_ACCESS_KEY_ID=AKIA... AWS_SECRET_ACCESS_KEY=... AWS_DEFAULT_REGION=us-east-1

echo ok | aws s3 cp - s3://download-joulescope-com/joulescope_install/_scope_test.txt  # succeeds
echo no | aws s3 cp - s3://download-joulescope-com/other/_scope_test.txt               # AccessDenied (expected)
```

The pipeline has no delete permission by design, so remove the test object with
admin credentials:

```bash
aws s3 rm s3://download-joulescope-com/joulescope_install/_scope_test.txt
```

## Local dry run (no credentials, no writes)

To preview what a release would change against the live index without any AWS
write access, stage the installers in `dist_installer/` and run:

```bash
python ci/publish.py --dry-run     # reads live index, prints planned writes
python ci/publish.py --local DIR   # writes the full tree to DIR, no AWS at all
```

See [`ci/test_publish.py`](test_publish.py) for the fully offline end-to-end
test of the publish + promote + consumer-update loop.

## Alternative: OIDC role assumption (no long-lived keys)

The `publish` job already requests `permissions: id-token: write`.  To avoid
long-lived access keys, attach the same policy
([`aws_publish_policy.json`](aws_publish_policy.json)) to an **IAM role** whose
trust policy allows the GitHub OIDC provider for this repo (e.g. scoped to
`repo:Jetperch/pyjoulescope_ui:ref:refs/tags/*`), and replace the static-key
`env:` block with an `aws-actions/configure-aws-credentials` step using
`role-to-assume`.  The `JOULESCOPE_DOWNLOAD_BUCKET` secret is still required.
