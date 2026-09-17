/** Convert the reviewed local Excel workbook into the ignored CER/WER gold CSV. */

import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = process.cwd();
const inputFileName = process.argv[2] ?? "ocr_gold_stratified_18pages.xlsx";
const inputPath = path.join(root, "output/evals/ocr-cer-wer/raw", inputFileName);
const outputPath = path.join(root, "output/evals/ocr-cer-wer/raw/gold_transcriptions.csv");
const headers = [
  "sample_id",
  "document_type",
  "source_path",
  "page_number",
  "reviewer_a_text",
  "reviewer_b_text",
  "adjudicated_text",
  "status",
  "approver",
  "approved_at",
];

function csvCell(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function text(value) {
  return value === null || value === undefined ? "" : String(value);
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheet = workbook.worksheets.getItem("검수 대장");
const values = sheet.getRange("A6:L1000").values;
const rows = values
  .filter((row) => text(row[0]).trim())
  .map((row) => ({
    sample_id: text(row[0]),
    document_type: text(row[1]),
    source_path: text(row[2]),
    page_number: text(row[3]),
    reviewer_a_text: text(row[4]),
    reviewer_a_status: text(row[5]),
    reviewer_b_text: text(row[6]),
    reviewer_b_status: text(row[7]),
    adjudicated_text: text(row[8]),
    final_status: text(row[9]),
    approved_at: text(row[10]),
  }));

if (!rows.length) throw new Error("review_workbook_has_no_rows");
const incomplete = rows.filter((row) =>
  row.reviewer_a_status !== "완료"
  || row.reviewer_b_status !== "완료"
  || row.final_status !== "확정",
);
if (incomplete.length) {
  throw new Error(`review_workbook_not_complete:${incomplete.length}`);
}
const emptyAdjudication = rows.filter((row) =>
  !row.adjudicated_text.trim() && (row.reviewer_a_text.trim() || row.reviewer_b_text.trim()),
);
if (emptyAdjudication.length) {
  throw new Error(`review_workbook_missing_adjudication:${emptyAdjudication.length}`);
}

const outputRows = rows.map((row) => [
  row.sample_id,
  row.document_type,
  row.source_path,
  row.page_number,
  row.reviewer_a_text,
  row.reviewer_b_text,
  row.adjudicated_text,
  "approved",
  "single_reviewer",
  row.approved_at,
]);
await fs.writeFile(
  outputPath,
  [headers, ...outputRows].map((row) => row.map(csvCell).join(",")).join("\n") + "\n",
  "utf8",
);

const byType = Object.fromEntries(
  [...new Set(rows.map((row) => row.document_type))]
    .sort((left, right) => left.localeCompare(right, "ko"))
    .map((documentType) => [documentType, rows.filter((row) => row.document_type === documentType).length]),
);
console.log(JSON.stringify({
  input: path.relative(root, inputPath),
  output: path.relative(root, outputPath),
  approved_pages: rows.length,
  by_document_type: byType,
  raw_text_persisted: true,
}, null, 2));
