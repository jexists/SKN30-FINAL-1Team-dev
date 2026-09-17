import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const sourcePath = path.join(root, "output/evals/ocr-cer-wer/raw/gold_transcription_template.csv");
const outputFileName = process.argv[2] ?? "ocr_gold_single_reviewer.xlsx";
const pagesPerType = Number(process.argv[3] ?? 0);
const outputPath = path.join(root, "output/evals/ocr-cer-wer/raw", outputFileName);

function parseCsv(text) {
  const rows = [];
  let row = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === '"') {
      if (quoted && text[index + 1] === '"') {
        value += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === "," && !quoted) {
      row.push(value);
      value = "";
    } else if (char === "\n" && !quoted) {
      row.push(value.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      value = "";
    } else {
      value += char;
    }
  }
  if (value || row.length) rows.push([...row, value]);
  return rows;
}

const csv = parseCsv(await fs.readFile(sourcePath, "utf8"));
const headers = csv[0];
const allRecords = csv.slice(1).filter((row) => row.length >= headers.length);
const indexOf = (name) => headers.indexOf(name);

function deterministicRank(value) {
  let hash = 0x811c9dc5;
  const seeded = `OCR-CER-WER-20260916:${value}`;
  for (const char of seeded) {
    hash ^= char.codePointAt(0);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash;
}

function selectStratified(records, countPerType) {
  if (!countPerType) return records;
  const grouped = new Map();
  for (const record of records) {
    const type = record[indexOf("document_type")];
    grouped.set(type, [...(grouped.get(type) ?? []), record]);
  }
  return [...grouped.entries()]
    .sort(([left], [right]) => left.localeCompare(right, "ko"))
    .flatMap(([, group]) => group
      .sort((left, right) => {
        const leftId = left[indexOf("sample_id")];
        const rightId = right[indexOf("sample_id")];
        return deterministicRank(leftId) - deterministicRank(rightId) || leftId.localeCompare(rightId, "ko");
      })
      .slice(0, countPerType));
}

const records = selectStratified(allRecords, pagesPerType);
const sampleDescription = pagesPerType
  ? `문서 유형별 ${pagesPerType}페이지의 고정 층화표본입니다. 전체 결과로 일반화하지 않고 표본 CER/WER로 보고합니다.`
  : "원본을 1차·2차로 독립 전사하고, 불일치 항목을 재검수해 확정합니다.";
const font = "Arial";
const navy = "#18324B";
const blue = "#2D6CDF";
const lightBlue = "#EAF2FF";
const paleYellow = "#FFF2CC";
const lightGray = "#F5F7FA";
const line = "#D8DEE7";

const workbook = Workbook.create();
const summary = workbook.worksheets.add("검수 요약");
const review = workbook.worksheets.add("검수 대장");
const guide = workbook.worksheets.add("사용 방법");

for (const sheet of [summary, review, guide]) {
  sheet.showGridLines = false;
  sheet.getRange("A1:M400").format.font = { name: font, size: 10, color: "#243444" };
}

summary.mergeCells("A2:H2");
summary.getRange("A2").values = [[pagesPerType ? "OCR CER/WER 60페이지 표본 전사 대장" : "OCR CER/WER 단일 검수자 전사 대장"]];
summary.getRange("A2").format = { font: { name: font, size: 16, bold: true, color: navy } };
summary.getRange("A3:H3").merge();
summary.getRange("A3").values = [[sampleDescription]];
summary.getRange("A3").format = { font: { name: font, size: 10, color: "#5E6B78", italic: true } };
summary.getRange("A5:H5").values = [[pagesPerType ? "표본 페이지" : "전체 페이지", "", "1차 완료", "", "확정 완료", "", "확정 필요", ""]];
summary.mergeCells("A5:B5");
summary.mergeCells("C5:D5");
summary.mergeCells("E5:F5");
summary.mergeCells("G5:H5");
summary.getRange("A5:H5").format = { fill: navy, font: { name: font, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center" };
summary.getRange("A6:H6").values = [[records.length, "", null, "", null, "", null, ""]];
summary.mergeCells("A6:B6");
summary.mergeCells("C6:D6");
summary.mergeCells("E6:F6");
summary.mergeCells("G6:H6");
summary.getRange("C6").formulas = [[`=COUNTIF('검수 대장'!$F$6:$F$${records.length + 5},"완료")`]];
summary.getRange("E6").formulas = [[`=COUNTIF('검수 대장'!$J$6:$J$${records.length + 5},"확정")`]];
summary.getRange("G6").formulas = [[`=A6-E6`]];
summary.getRange("A5:H6").format.borders = { preset: "all", style: "thin", color: line };
summary.getRange("A6:H6").format = { fill: lightBlue, font: { name: font, size: 12, bold: true, color: navy }, horizontalAlignment: "center", verticalAlignment: "center" };
summary.getRange("A8:H8").merge();
summary.getRange("A8").values = [["검수 순서"]];
summary.getRange("A8").format = { fill: navy, font: { name: font, bold: true, color: "#FFFFFF" } };
summary.getRange("A9:H12").values = [
  ["1", "1차 전사", "원본만 보고 `1차 전사`를 입력한 뒤 `1차 상태`를 완료로 변경합니다.", "", "", "", "", ""],
  ["2", "시간 간격", "다른 문서 작업 후 최소 하루가 지난 뒤 2차 전사를 진행합니다.", "", "", "", "", ""],
  ["3", "2차 전사", "원본만 보고 `2차 전사`를 입력한 뒤 `2차 상태`를 완료로 변경합니다.", "", "", "", "", ""],
  ["4", "확정", "일치 판정이 재검수인 행은 원본을 다시 보고 `확정 전사`를 입력한 뒤 `확정 상태`를 확정으로 변경합니다.", "", "", "", "", ""],
];
summary.getRange("A9:H12").format.wrapText = true;
for (let row = 9; row <= 12; row += 1) summary.mergeCells(`C${row}:H${row}`);
summary.getRange("A9:H12").format.borders = { preset: "all", style: "thin", color: line };
summary.getRange("A9:A12").format = { fill: lightBlue, font: { name: font, bold: true, color: navy }, horizontalAlignment: "center" };
summary.getRange("B9:B12").format.font = { name: font, bold: true, color: navy };
summary.getRange("A14:H14").merge();
summary.getRange("A14").values = [["판정 기준"]];
summary.getRange("A14").format = { fill: navy, font: { name: font, bold: true, color: "#FFFFFF" } };
summary.getRange("A15:H17").values = [
  ["전사 기준", "원본에 보이는 문자·숫자·기호를 전사합니다. 읽을 수 없는 글자는 □로 표시합니다.", "", "", "", "", "", ""],
  ["CER/WER 조건", "모든 행이 확정 상태여야 계산합니다. OCR 출력은 전사 정답을 작성할 때 보지 않습니다.", "", "", "", "", "", ""],
  ["발표 표기", pagesPerType ? `문서 유형별 ${pagesPerType}페이지의 고정 층화표본, 단일 검수자 2회 독립 전사·불일치 재검수 골드셋이라고 표기합니다.` : "단일 검수자 2회 독립 전사·불일치 재검수로 작성한 골드셋이라고 표기합니다.", "", "", "", "", "", ""],
];
summary.getRange("A15:H17").format.wrapText = true;
for (let row = 15; row <= 17; row += 1) summary.mergeCells(`B${row}:H${row}`);
summary.getRange("A15:H17").format.borders = { preset: "all", style: "thin", color: line };
summary.getRange("A15:A17").format = { fill: lightGray, font: { name: font, bold: true, color: navy } };
summary.getRange("A:A").format.columnWidth = 14;
summary.getRange("B:B").format.columnWidth = 17;
summary.getRange("C:C").format.columnWidth = 15;
summary.getRange("D:D").format.columnWidth = 15;
summary.getRange("E:E").format.columnWidth = 15;
summary.getRange("F:F").format.columnWidth = 15;
summary.getRange("G:G").format.columnWidth = 15;
summary.getRange("H:H").format.columnWidth = 15;
summary.getRange("A2:H17").format.verticalAlignment = "center";
summary.getRange("A9:H12").format.rowHeight = 34;
summary.getRange("A15:H17").format.rowHeight = 28;

review.mergeCells("A1:M1");
review.getRange("A1").values = [[pagesPerType ? "OCR CER/WER 60페이지 표본 전사 검수 대장" : "OCR CER/WER 전사 검수 대장"]];
review.getRange("A1").format = { font: { name: font, size: 14, bold: true, color: navy } };
review.mergeCells("A2:M2");
review.getRange("A2").values = [["노란색 열만 작성합니다. OCR 결과를 보지 말고 원본 파일과 페이지를 확인합니다."]];
review.getRange("A2").format = { font: { name: font, size: 10, color: "#5E6B78", italic: true } };
review.mergeCells("A3:M3");
review.getRange("A3").values = [["원본 상대 경로는 저장소 루트 기준입니다. 빈 페이지도 상태를 완료·확정으로 표시합니다."]];
review.getRange("A3").format = { font: { name: font, size: 9, color: "#5E6B78" } };
const reviewHeaders = ["표본 ID", "문서 유형", "원본 상대 경로", "페이지", "1차 전사", "1차 상태", "2차 전사", "2차 상태", "확정 전사", "확정 상태", "검수일", "메모", "일치 판정"];
review.getRange("A5:M5").values = [reviewHeaders];
review.getRange("A5:M5").format = { fill: navy, font: { name: font, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
const dataRows = records.map((record, offset) => {
  const row = offset + 6;
  return [
    record[indexOf("sample_id")],
    record[indexOf("document_type")],
    record[indexOf("source_path")],
    Number(record[indexOf("page_number")]),
    "",
    "대기",
    "",
    "대기",
    "",
    "대기",
    "",
    "",
    `=IF(AND(F${row}="완료",H${row}="완료"),IF(E${row}=G${row},"일치","재검수"),"대기")`,
  ];
});
review.getRange(`A6:M${records.length + 5}`).values = dataRows.map((row) => row.slice(0, 12));
review.getRange(`M6:M${records.length + 5}`).formulas = dataRows.map((row) => [row[12]]);
review.getRange(`A5:M${records.length + 5}`).format.borders = { preset: "all", style: "thin", color: line };
review.getRange(`E6:L${records.length + 5}`).format.wrapText = true;
review.getRange(`E6:E${records.length + 5}`).format.fill = paleYellow;
review.getRange(`F6:F${records.length + 5}`).format.fill = paleYellow;
review.getRange(`G6:G${records.length + 5}`).format.fill = paleYellow;
review.getRange(`H6:H${records.length + 5}`).format.fill = paleYellow;
review.getRange(`I6:I${records.length + 5}`).format.fill = paleYellow;
review.getRange(`J6:J${records.length + 5}`).format.fill = paleYellow;
review.getRange(`K6:K${records.length + 5}`).format.fill = paleYellow;
review.getRange(`L6:L${records.length + 5}`).format.fill = paleYellow;
review.getRange(`F6:F${records.length + 5}`).dataValidation = { rule: { type: "list", values: ["대기", "완료"] } };
review.getRange(`H6:H${records.length + 5}`).dataValidation = { rule: { type: "list", values: ["대기", "완료"] } };
review.getRange(`J6:J${records.length + 5}`).dataValidation = { rule: { type: "list", values: ["대기", "확정"] } };
review.getRange(`D6:D${records.length + 5}`).format.numberFormat = "0";
review.getRange(`K6:K${records.length + 5}`).format.numberFormat = "yyyy-mm-dd";
review.getRange(`A6:D${records.length + 5}`).format.verticalAlignment = "center";
review.getRange(`M6:M${records.length + 5}`).format.horizontalAlignment = "center";
review.getRange(`M6:M${records.length + 5}`).conditionalFormats.add("containsText", { text: "재검수", format: { fill: "#FCE4D6", font: { bold: true, color: "#C00000" } } });
review.freezePanes.freezeRows(5);
review.freezePanes.freezeColumns(4);
const widths = [30, 14, 49, 9, 44, 12, 44, 12, 44, 12, 13, 24, 13];
for (let index = 0; index < widths.length; index += 1) {
  review.getRangeByIndexes(0, index, records.length + 5, 1).format.columnWidth = widths[index];
}
review.getRange(`A6:M${records.length + 5}`).format.rowHeight = 28;

guide.mergeCells("A2:H2");
guide.getRange("A2").values = [[pagesPerType ? "60페이지 표본 CER/WER 전사 방법" : "단일 검수자 CER/WER 전사 방법"]];
guide.getRange("A2").format = { font: { name: font, size: 16, bold: true, color: navy } };
guide.getRange("A4:H4").merge();
guide.getRange("A4").values = [[pagesPerType ? `계약서·발주서·사업자등록증에서 각 ${pagesPerType}페이지를 고정 추출했습니다. 검수자가 한 명일 때는 2회 독립 전사와 불일치 재검수로 전사 오류를 줄입니다.` : "검수자가 한 명일 때는 2회 독립 전사와 불일치 재검수로 전사 오류를 줄입니다."]];
guide.getRange("A4").format = { font: { name: font, size: 10, color: "#5E6B78", italic: true } };
guide.getRange("A6:H10").values = [
  ["단계", "작업", "입력 위치", "완료 기준", "", "", "", ""],
  ["1차", "원본 화면만 보고 모든 페이지를 전사", "검수 대장 E열·F열", "F열을 완료로 설정", "", "", "", ""],
  ["간격", "최소 하루 후 2차 전사 시작", "", "1차 전사 내용을 보지 않음", "", "", "", ""],
  ["2차", "원본 화면만 보고 다시 전사", "검수 대장 G열·H열", "H열을 완료로 설정", "", "", "", ""],
  ["확정", "일치 판정이 재검수인 행만 원본 재확인", "검수 대장 I열·J열", "J열을 확정으로 설정", "", "", "", ""],
];
guide.getRange("A6:H6").format = { fill: navy, font: { name: font, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
guide.getRange("A6:H10").format.borders = { preset: "all", style: "thin", color: line };
guide.getRange("A7:A10").format = { fill: lightBlue, font: { name: font, bold: true, color: navy } };
guide.getRange("A12:H12").merge();
guide.getRange("A12").values = [["전사 규칙"]];
guide.getRange("A12").format = { fill: navy, font: { name: font, bold: true, color: "#FFFFFF" } };
guide.getRange("A13:H17").values = [
  ["문자", "보이는 문자·숫자·기호를 그대로 전사합니다.", "", "", "", "", "", ""],
  ["읽기 불가", "판독할 수 없는 문자는 추정하지 말고 □로 표시합니다.", "", "", "", "", "", ""],
  ["표", "위에서 아래, 왼쪽에서 오른쪽 순으로 전사합니다.", "", "", "", "", "", ""],
  ["공백", "줄바꿈은 입력해도 됩니다. CER 계산 시 공백 하나로 정규화합니다.", "", "", "", "", "", ""],
  ["배제", "OCR 결과와 기존 요약은 전사 정답을 작성할 때 보지 않습니다.", "", "", "", "", "", ""],
];
guide.getRange("A13:H17").format.borders = { preset: "all", style: "thin", color: line };
guide.getRange("A13:A17").format = { fill: lightGray, font: { name: font, bold: true, color: navy } };
guide.getRange("A1:H20").format.verticalAlignment = "center";
guide.getRange("A:A").format.columnWidth = 14;
guide.getRange("B:B").format.columnWidth = 28;
guide.getRange("C:C").format.columnWidth = 25;
guide.getRange("D:D").format.columnWidth = 24;
guide.getRange("E:H").format.columnWidth = 12;
guide.getRange("A7:H10").format.rowHeight = 32;
guide.getRange("A13:H17").format.rowHeight = 26;

workbook.recalculate();
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(JSON.stringify({ outputPath, pageCount: records.length }));
