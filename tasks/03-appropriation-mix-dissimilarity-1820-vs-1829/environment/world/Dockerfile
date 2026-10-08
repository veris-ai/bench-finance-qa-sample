FROM ghcr.io/veris-ai/bench-finance-qa-sample/bundle@sha256:1451e852ad53db203156e6c3fbca1e654dc355124613d002ad4526b697205e44
COPY baseline/ /baseline/
# This world's blobs are supplied by the task: /veris/blobs/5h2ylsgcxqer1w0vhebyqop33/<sha256>, readable by uid 10001.
ENV VERIS_BLOB_REMOTE=file:///veris/blobs \
    VERIS_ENVIRONMENT_ID=5h2ylsgcxqer1w0vhebyqop33 \
    VERIS_BUNDLE_SERVICES=dropbox:6200 \
    SANDBOX_ID=world \
    VERIS_DATA_PLANE_CONTROL=off \
    VERIS_CONTROL_SPLIT=on \
    VERIS_CONTROL_HOST=127.0.0.1 \
    VERIS_SANDBOX_SECRET=622d358ce95b11c32c742022395144a5ddf319504cd919e3dfbd3bae6cd44c98
# Added by the Veris Bench Harbor exporter.
COPY harbor_collect.py /veris/harbor_collect.py
ENV VERIS_WORLD_START="2026-10-06T20:53:19Z"
USER root
RUN --mount=type=bind,source=harbor_fetch_blobs.py,target=/tmp/harbor_fetch_blobs.py \
    export HF_HOME=/tmp/hf-home \
    && pip install --no-cache-dir --target /tmp/hf 'huggingface_hub==2.1.1' \
    && PYTHONPATH=/tmp/hf python /tmp/harbor_fetch_blobs.py veris-ai/finance-qa-corpus 5h2ylsgcxqer1w0vhebyqop33 --root /veris/blobs --manifest /baseline/revision.json --revision 9e4037a2c23f08c64fda3fc76f895230c7115a36 \
    && rm -rf /tmp/hf /tmp/hf-home /veris/blobs/.cache \
    && chmod -R a+rX /veris/blobs
USER 10001
