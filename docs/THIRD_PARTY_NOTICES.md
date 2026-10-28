# Third-party license and attribution notes

**Review date:** 2026-10-28. License identifiers below were checked against PyPI metadata for the exact versions pinned in `pyproject.toml`; this is a direct-dependency inventory, not a complete transitive Software Bill of Materials. Preserve each upstream license and notice with any redistributed wheels or images. The project’s [`LICENSE`](../LICENSE) applies only to original repository code; it does not relicense dependencies, model weights, or the dataset.

## Direct runtime dependencies

| Package / pinned version | Declared license | Package metadata |
|---|---|---|
| FastAPI 0.162.0 | MIT | [PyPI](https://pypi.org/project/fastapi/0.162.0/) |
| Starlette 1.10.0 | BSD-3-Clause | [PyPI](https://pypi.org/project/starlette/1.10.0/) |
| Uvicorn 0.34.2 | BSD-3-Clause | [PyPI](https://pypi.org/project/uvicorn/0.34.2/) |
| Qdrant Client 1.20.0 | Apache-2.0 | [PyPI](https://pypi.org/project/qdrant-client/1.20.0/) |
| FastEmbed 0.9.1 | Apache-2.0 | [PyPI](https://pypi.org/project/fastembed/0.9.1/) |
| pypdf 6.21.3 | BSD-3-Clause | [PyPI](https://pypi.org/project/pypdf/6.21.3/) |
| python-docx 1.1.2 | MIT | [PyPI](https://pypi.org/project/python-docx/1.1.2/) |
| python-multipart 0.0.32 | Apache-2.0 | [PyPI](https://pypi.org/project/python-multipart/0.0.32/) |
| python-dotenv 1.2.4 | BSD-3-Clause | [PyPI](https://pypi.org/project/python-dotenv/1.2.4/) |
| SQLAlchemy 2.0.41 | MIT | [PyPI](https://pypi.org/project/SQLAlchemy/2.0.41/) |
| HTTPX 0.28.1 | BSD-3-Clause | [PyPI](https://pypi.org/project/httpx/0.28.1/) |
| Pillow 13.0.0 | MIT-CMU | [PyPI](https://pypi.org/project/pillow/13.0.0/) |

## Optional dependencies

- The `postgres` extra installs `psycopg[binary]==3.2.9`; both `psycopg` and `psycopg-binary` declare LGPL-3.0 ([versioned upstream source](https://github.com/psycopg/psycopg/tree/3.2.9)). The local SQLite workflow does not install this extra. The Dockerfile selects it for PostgreSQL Compose, retains the wheel-provided license texts under `/app/third_party_licenses/`, and includes this notice file. A redistributed image must satisfy the applicable source and relinking/replacement requirements for that library. Review the actual wheel/image contents and applicable obligations before external redistribution.
- The `test` extra includes pytest 9.2.0 (MIT), HTTPX2 2.16.0 (BSD-3-Clause), and Ruff 0.11.11 (MIT); see their versioned [PyPI project pages](https://pypi.org/project/pytest/9.2.0/), [HTTPX2](https://pypi.org/project/httpx2/2.16.0/), and [Ruff](https://pypi.org/project/ruff/0.11.11/).

The Docker Compose file also references separate PostgreSQL and Qdrant upstream container images; their licenses and notices remain applicable to those images and are not covered by this repository’s MIT license.

## Data and model

- The NIST SP 800-82 Rev. 3 source and its U.S. government/publication reuse notice, including third-party contribution caveats, are described in [`DATASET.md`](DATASET.md). The PDF is intentionally not redistributed in this repository.
- The `BAAI/bge-small-en-v1.5` embedding model is MIT-licensed; its model card and attribution are linked from [`DATASET.md`](DATASET.md). Model weights are downloaded from the upstream model registry at runtime and are not committed here.

## Scope and release checks

Permissive direct dependency licenses can generally be used alongside MIT-licensed original code while keeping their notices. The optional LGPL PostgreSQL binding has additional distribution conditions described above; it remains a separate dependency and the project source is not relicensed. This inventory does not cover the full transitive dependency graph, operating-system packages, or embedded third-party materials inside upstream data. Before a production release, generate an SBOM, scan all resolved package and container layers for their license texts, and obtain qualified review for the actual distribution model. This file is compliance documentation, not legal advice.
