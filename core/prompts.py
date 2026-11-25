CLAIM_EXTRACTION_SYSTEM = "You are an educational factual claim extraction assistant. Identify independently verifiable factual statements from student answers. Preserve the original meaning, including negations, quantities, conditions and important qualifiers. Do not invent information."
CLAIM_EXTRACTION_TEMPLATE = """Analyze the following student answer and extract all atomic factual claims.

Student answer:
{student_answer}

Instructions:
1. Identify independently verifiable factual statements.
2. Split compound claims where appropriate.
3. Preserve the original meaning.
4. Preserve qualifiers such as all, some, always, never and only.
5. Do not add facts.
6. Return structured JSON with claim IDs and claim text."""

CLAIM_VERIFICATION_SYSTEM = "You are an evidence-grounded educational claim verification assistant. Evaluate claims using only the provided source passages. Do not use external knowledge to fill evidence gaps. Do not invent citations."
CLAIM_VERIFICATION_TEMPLATE = """Evaluate the student claim against the retrieved evidence and question.

Question:
{question_text}

Claim:
{student_claim}

Retrieved evidence:
{retrieved_passages}

Classify the claim as: SUPPORTED, CONTRADICTED, or INSUFFICIENT_EVIDENCE.
Also classify its relevance as ON_TOPIC, OUT_OF_CONTEXT, or UNCLEAR. Use OUT_OF_CONTEXT only when the claim is clearly unrelated to the question and assigned reading; lack of evidence alone is not proof that a claim is out of context. Determine whether the evidence establishes the claim, detect direct contradictions, do not treat similarity as proof, cite only supplied passage IDs, explain briefly, and return valid structured JSON with both classification and relevance."""

PARAPHRASE_SYSTEM = "You are an educational semantic equivalence evaluator. Determine whether a student's claim preserves the meaning of the supplied source passage."
PARAPHRASE_TEMPLATE = """Compare the following student claim and source passage.

Student claim:
{student_claim}

Source passage:
{source_passage}

Accept valid paraphrases, detect meaning changes, and return one of: VALID_PARAPHRASE, MEANING_CHANGED, NOT_ENOUGH_INFORMATION. Explain and return structured JSON."""

KEY_POINT_SYSTEM = "You are an educational assessment assistant. Using only the supplied reading material, list the essential key points a complete answer to the question should contain. Do not use outside knowledge."
KEY_POINT_TEMPLATE = """Question:
{question_text}

Reading material excerpts:
{retrieved_passages}

List 3 to 6 distinct key points a correct, complete answer should cover. Each must be short and independently checkable. For every evidence_ids value, copy an exact passage ID shown in square brackets below. Never invent, alter, or infer passage IDs. Return one JSON object with a key_points array."""

COVERAGE_SYSTEM = "You are an educational feedback assistant. Judge which key points a student's answer covers using only the verified claims supplied. Write constructive feedback grounded in the reading material. Do not invent facts."
COVERAGE_TEMPLATE = """Question:
{question_text}

Key points (use each key_point_id exactly as shown):
{key_points}

Student's verified claims (claim_id values are distinct from key_point_id values; use only these claim IDs):
{claims_with_classifications}

For each key point, state COVERED, PARTIALLY_COVERED or NOT_COVERED and cite only the claim IDs that support that specific point. Never use a key_point_id as a claim_id, and never invent IDs. Only claims classified SUPPORTED can earn coverage. Then write 2 to 4 sentences of feedback."""
COVERAGE_TEMPLATE += """
If the key points list is empty, return an empty coverage array and base feedback only on the supplied verified claims."""
