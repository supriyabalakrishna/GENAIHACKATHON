import csv, io, json

def claim_report_rows(db, submission_id: int) -> list[dict]:
    from database.models import Claim, Citation, Document, Evaluation
    from core.vector_store import get_collection

    claims = db.query(Claim).filter(Claim.submission_id == submission_id).order_by(Claim.claim_order).all()
    evaluations = {
        evaluation.claim_id: evaluation
        for evaluation in db.query(Evaluation).join(Claim).filter(Claim.submission_id == submission_id).all()
    }
    citations = {}
    for citation in db.query(Citation).join(Evaluation).join(Claim).filter(Claim.submission_id == submission_id).all():
        citations.setdefault(citation.evaluation_id, []).append(citation)

    chunk_ids = list(dict.fromkeys(
        citation.chunk_id
        for rows in citations.values()
        for citation in rows
    ))
    stored_passages = {}
    if chunk_ids:
        collection_result = get_collection().get(ids=chunk_ids, include=["documents", "metadatas"])
        stored_passages = {
            chunk_id: {"text": text, "metadata": metadata}
            for chunk_id, text, metadata in zip(
                collection_result["ids"],
                collection_result["documents"],
                collection_result["metadatas"],
            )
        }

    rows = []
    for claim in claims:
        evaluation = evaluations.get(claim.id)
        claim_citations = citations.get(evaluation.id, []) if evaluation else []
        evidence = []
        for citation in claim_citations:
            passage = stored_passages.get(citation.chunk_id, {})
            metadata = passage.get("metadata", {})
            document = db.get(Document, citation.document_id)
            file_type = document.file_type.lower() if document else ""
            page_number = citation.page_number
            if file_type == "pptx":
                location = f"Slide {page_number}" if page_number else "n/a"
            elif file_type == "pdf":
                location = f"Page {page_number}" if page_number else "n/a"
            else:
                location = "n/a"
            evidence.append({
                "chunk_id": citation.chunk_id,
                "document_name": document.filename if document else metadata.get("document_name", "Source document"),
                "location": location,
                "text": passage.get("text", "The cited source passage is no longer available."),
            })
        rows.append({
            "claim_id": claim.claim_order,
            "claim_text": claim.claim_text,
            "classification": evaluation.classification if evaluation else "INSUFFICIENT_EVIDENCE",
            "relevance": evaluation.relevance if evaluation else "UNCLEAR",
            "explanation": evaluation.explanation if evaluation else "No verification result was saved.",
            "review_required": bool(evaluation.review_required) if evaluation else True,
            "citations": evidence,
            "evidence_ids": [item["chunk_id"] for item in evidence],
        })
    return rows

def report_csv(report: dict) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["student", "assignment", "question", "claim", "classification", "relevance", "explanation", "document", "page_or_slide", "passage"])
    for claim in report["claims"]:
        citations = claim.get("citations") or [{}]
        for citation in citations:
            writer.writerow([
                report["student"], report["assignment"], report["question"], claim["claim_text"],
                claim["classification"], claim.get("relevance", "UNCLEAR"), claim["explanation"], citation.get("document_name", ""),
                citation.get("location", ""), citation.get("text", ""),
            ])
    return output.getvalue()

def report_json(report: dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False)
