# Corpus and model provenance

## Selected source

The seed corpus is NIST Special Publication 800-82 Revision 3, *Guide to Operational Technology (OT) Security*, published September 2023. NIST describes it as guidance for securing operational technology while addressing performance, reliability, and safety. The authoritative publication page is <https://csrc.nist.gov/pubs/sp/800/82/r3/final>; the source PDF is <https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-82r3.pdf>. Publisher: National Institute of Standards and Technology (NIST), U.S. Department of Commerce. File type: text PDF. The original PDF has 316 physical PDF pages and was 8,584,345 bytes when downloaded for this run; SHA-256: `608f554514d381853e24e0b33123b7080fbd757826f460032690aade63394616`. Retrieval date: 2026-10-28.

NIST’s publication front matter states that SP 800-82 Rev. 3 may be used voluntarily by nongovernmental organizations and is not subject to copyright in the United States, with attribution appreciated. NIST’s general reuse policy distinguishes works authored by NIST employees from works authored by third parties and notes foreign rights may differ. The report credits contributors from both NIST and MITRE and acknowledges reused material from CPNI and ISA. Therefore, this project downloads and processes the handbook locally, does not redistribute the PDF, images, or full extracted text, and limits its public artifact to source links, bibliographic facts, page/chunk metadata, and short answer excerpts generated at runtime. Review source front matter and any third-party markings before production redistribution or use outside the United States. Sources: <https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-82r3.pdf> and <https://www.nist.gov/open/license>.

Intended use: portfolio demonstration of grounded search over publicly accessible OT-security guidance. This is not an approved NIST product, does not imply NIST endorsement, and must not be used as the sole authority for operational or safety-critical decisions.

## Reproducible acquisition

Run `python scripts/download_data.py`. The downloader uses only the canonical NIST publications PDF URL, refuses non-PDF responses, limits downloads to 25 MB, and stores the document at `data/raw/NIST.SP.800-82r3.pdf`. The raw PDF is excluded from Git. Then run `python scripts/index_documents.py` to extract and index pages, or upload the same file through the web UI. The manifest entry is represented here and in `data/manifest.json`; both the source and model files remain external to the repository.

The acquisition procedure was executed on 2026-10-28. It retrieved the 8.58 MB PDF successfully and checked the PDF signature, file size, and SHA-256. PDF text extraction was verified using `pdftotext`; the source is tagged and not an image-only scan. Scanned PDFs currently fail clearly with an OCR-not-enabled message.

## Embedding model

`BAAI/bge-small-en-v1.5` is used through the FastEmbed ONNX runtime, on CPU by default. FastEmbed’s supported-model catalog lists the model as MIT-licensed, English, 384 dimensions, and approximately 67 MB. Model card: <https://huggingface.co/BAAI/bge-small-en-v1.5>. It is downloaded on first index/query and cached outside the repository. Model license and technical attributes: <https://qdrant.github.io/fastembed/>. Only model weights are used; this repository does not train or redistribute them.

The upstream BGE model card states an MIT license and 384-dimensional embeddings: <https://huggingface.co/BAAI/bge-small-en-v1.5>. FastEmbed's model registry documents supported model names and runtime behavior: <https://qdrant.github.io/fastembed/>.
