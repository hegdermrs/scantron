const form = document.getElementById("omr-form");
const fileInput = document.getElementById("file-input");
const startCameraButton = document.getElementById("start-camera");
const capturePhotoButton = document.getElementById("capture-photo");
const stopCameraButton = document.getElementById("stop-camera");
const submitButton = document.getElementById("submit-button");
const cameraFeed = document.getElementById("camera-feed");
const captureCanvas = document.getElementById("capture-canvas");
const cameraPlaceholder = document.getElementById("camera-placeholder");
const previewEmpty = document.getElementById("preview-empty");
const previewCard = document.getElementById("preview-card");
const previewImage = document.getElementById("preview-image");
const previewName = document.getElementById("preview-name");
const previewSize = document.getElementById("preview-size");
const previewSource = document.getElementById("preview-source");
const statusBox = document.getElementById("status-box");
const resultsPage = document.getElementById("results-page");
const resultSummary = document.getElementById("result-summary");
const resultNotes = document.getElementById("result-notes");
const resultSubmissionId = document.getElementById("result-submission-id");
const resultTestCode = document.getElementById("result-test-code");
const resultStatus = document.getElementById("result-status");
const resultMethod = document.getElementById("result-method");
const resultScore = document.getElementById("result-score");
const resultPercent = document.getElementById("result-percent");
const resultConfidence = document.getElementById("result-confidence");
const resultPageFound = document.getElementById("result-page-found");
const sectionScoresGrid = document.getElementById("section-scores");
const sectionScoresEmpty = document.getElementById("section-scores-empty");
const answersEmpty = document.getElementById("answers-empty");
const answersGrid = document.getElementById("answers-grid");

let activeStream = null;
let selectedFile = null;
let selectedSource = "";

const webhookUrl = getConfiguredWebhookUrl();

bindEvents();
reportMissingWebhookConfig();
updateSubmitState();

function bindEvents() {
  fileInput.addEventListener("change", handleFileSelection);
  startCameraButton.addEventListener("click", startCamera);
  capturePhotoButton.addEventListener("click", capturePhoto);
  stopCameraButton.addEventListener("click", stopCamera);
  form.addEventListener("submit", submitOmrSheet);
  window.addEventListener("beforeunload", stopCamera);
}

function getConfiguredWebhookUrl() {
  const configuredUrl = window.APP_CONFIG?.webhookUrl;
  return typeof configuredUrl === "string" ? configuredUrl.trim() : "";
}

function reportMissingWebhookConfig() {
  if (!webhookUrl) {
    setStatus("Submission is not available right now. Please contact the administrator.", "error");
  }
}

function handleFileSelection(event) {
  const [file] = event.target.files || [];
  if (!file) {
    return;
  }

  selectedFile = file;
  selectedSource = "upload";
  stopCamera();
  renderPreview(file, selectedSource);
  clearRenderedResult();
  setStatus("Image selected. Review it and submit when ready.", "info");
  updateSubmitState();
}

async function startCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setStatus("This browser does not support camera access. Please upload an image instead.", "error");
    return;
  }

  try {
    stopCamera();

    activeStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false,
    });

    cameraFeed.srcObject = activeStream;
    cameraFeed.hidden = false;
    cameraPlaceholder.hidden = true;

    await cameraFeed.play();

    capturePhotoButton.disabled = false;
    stopCameraButton.disabled = false;
    setStatus("Camera is live. Line up the OMR sheet and capture when ready.", "info");
  } catch (error) {
    setStatus(
      "Could not open the camera. On phones, open this page over HTTPS or localhost and allow camera permission.",
      "error"
    );
  }
}

function stopCamera() {
  if (activeStream) {
    activeStream.getTracks().forEach((track) => track.stop());
    activeStream = null;
  }

  cameraFeed.pause();
  cameraFeed.srcObject = null;
  cameraFeed.hidden = true;
  cameraPlaceholder.hidden = false;
  capturePhotoButton.disabled = true;
  stopCameraButton.disabled = true;
}

async function capturePhoto() {
  if (!activeStream) {
    return;
  }

  const width = cameraFeed.videoWidth;
  const height = cameraFeed.videoHeight;

  if (!width || !height) {
    setStatus("Camera is not ready yet. Please wait a moment and try again.", "error");
    return;
  }

  captureCanvas.width = width;
  captureCanvas.height = height;

  const context = captureCanvas.getContext("2d");
  context.drawImage(cameraFeed, 0, 0, width, height);

  const blob = await new Promise((resolve) => captureCanvas.toBlob(resolve, "image/jpeg", 0.92));
  if (!blob) {
    setStatus("Could not capture the photo. Please try again.", "error");
    return;
  }

  selectedFile = new File([blob], `omr-capture-${Date.now()}.jpg`, { type: "image/jpeg" });
  selectedSource = "camera";
  renderPreview(selectedFile, selectedSource);
  clearRenderedResult();
  setStatus("Photo captured. Review it and submit when ready.", "info");
  updateSubmitState();
}

function renderPreview(file, source) {
  const objectUrl = URL.createObjectURL(file);
  previewImage.src = objectUrl;
  previewImage.onload = () => URL.revokeObjectURL(objectUrl);

  previewName.textContent = file.name;
  previewSize.textContent = formatBytes(file.size);
  previewSource.textContent = source === "camera" ? "Camera" : "Upload";

  previewEmpty.hidden = true;
  previewCard.hidden = false;
}

async function submitOmrSheet(event) {
  event.preventDefault();

  if (!webhookUrl) {
    setStatus("Submission is not available right now. Please contact the administrator.", "error");
    return;
  }

  if (!selectedFile) {
    setStatus("Select or capture an OMR sheet before submitting.", "error");
    return;
  }

  submitButton.disabled = true;
  setStatus("Submitting your OMR sheet...", "info");

  const formData = new FormData();
  formData.append("file", selectedFile);
  formData.append("source", selectedSource);
  formData.append("submittedAt", new Date().toISOString());

  try {
    const response = await fetch(webhookUrl, {
      method: "POST",
      body: formData,
    });

    const responseText = await response.text();
    if (!response.ok) {
      throw new Error(responseText || `Request failed with status ${response.status}`);
    }

    const parsedResult = parseWebhookResponse(responseText);
    if (parsedResult) {
      renderSubmissionResult(parsedResult);
    } else {
      clearRenderedResult();
    }

    const friendlyResponse = parsedResult
      ? buildResultStatusMessage(parsedResult)
      : responseText
        ? truncate(responseText, 160)
        : "Your sheet was submitted successfully.";
    setStatus(`Submission successful. ${friendlyResponse}`, "success");
  } catch (error) {
    setStatus(`Submission failed. Please try again. ${error.message}`, "error");
  } finally {
    updateSubmitState();
  }
}

function updateSubmitState() {
  submitButton.disabled = !selectedFile || !webhookUrl;
}

function parseWebhookResponse(responseText) {
  if (!responseText) {
    return null;
  }

  try {
    const parsed = JSON.parse(responseText);
    return Array.isArray(parsed) ? parsed[0] || null : parsed;
  } catch (error) {
    return null;
  }
}

function renderSubmissionResult(result) {
  const normalizedResult = normalizeResultPayload(result);
  const answers = normalizeAnswers(normalizedResult.finalAnswers);
  const scoreValue = normalizedResult.score !== null && normalizedResult.total !== null
    ? `${normalizedResult.score}/${normalizedResult.total}`
    : "-";
  const percentValue = normalizedResult.percent !== null
    ? `${normalizedResult.percent}%`
    : "-";

  resultSummary.textContent = normalizedResult.compositeComputed
    ? `Composite score ready for ${normalizedResult.testName || "this ACT form"}.`
    : "The sheet was processed, but the composite score could not be calculated yet.";
  resultNotes.textContent = normalizedResult.notes || "Section scores and detected answers are shown below.";
  resultSubmissionId.textContent = normalizedResult.submissionId || "-";
  resultTestCode.textContent = normalizedResult.testCode || normalizedResult.testName || "-";
  resultStatus.textContent = normalizedResult.finalStatus || "processed";
  resultMethod.textContent = normalizedResult.finalMethod || "-";
  resultScore.textContent = scoreValue;
  resultPercent.textContent = percentValue;
  resultConfidence.textContent = normalizedResult.confidence !== null
    ? `${Math.round(normalizedResult.confidence * 100)}%`
    : "-";
  resultPageFound.textContent = normalizedResult.pageFound === null
    ? "-"
    : normalizedResult.pageFound ? "Yes" : "No";

  renderSectionScores(normalizedResult.sectionScores);

  answersGrid.innerHTML = "";

  if (answers.length === 0) {
    answersEmpty.hidden = false;
    answersGrid.hidden = true;
  } else {
    answers.forEach(([question, answer]) => {
      const item = document.createElement("div");
      item.className = `answer-chip answer-${answerState(answer)}`;

      const label = document.createElement("span");
      label.className = "meta-label";
      label.textContent = question;
      item.append(label);

      const value = document.createElement("strong");
      value.textContent = answer;
      item.append(value);

      answersGrid.append(item);
    });

    answersEmpty.hidden = true;
    answersGrid.hidden = false;
  }

  resultsPage.hidden = false;
  resultsPage.scrollIntoView({ behavior: "smooth", block: "start" });
}

function clearRenderedResult() {
  resultsPage.hidden = true;
  resultSummary.textContent = "Your processed OMR result will appear here.";
  resultNotes.textContent = "Detailed scoring and detected answers will appear below.";
  resultSubmissionId.textContent = "-";
  resultTestCode.textContent = "-";
  resultStatus.textContent = "-";
  resultMethod.textContent = "-";
  resultScore.textContent = "-";
  resultPercent.textContent = "-";
  resultConfidence.textContent = "-";
  resultPageFound.textContent = "-";
  sectionScoresGrid.innerHTML = "";
  sectionScoresGrid.hidden = true;
  sectionScoresEmpty.hidden = false;
  answersGrid.innerHTML = "";
  answersGrid.hidden = true;
  answersEmpty.hidden = false;
}

function normalizeResultPayload(result) {
  const parsedAnswersJson = parseAnswersValue(result["Answers JSON"]);
  const finalAnswers = parseAnswersValue(result.finalAnswers || result.answers) || parsedAnswersJson || {};

  return {
    submissionId: result.submissionId || result["Submission ID"] || "",
    testCode: result.testCode || result["Test Code"] || "",
    testName: result.testName || result["Test Name"] || result.version || "",
    finalStatus: result.finalStatus || result.status || result["Status"] || "processed",
    finalMethod: result.finalMethod || result.method || result.variant || result["OMR Method"] || "-",
    confidence: normalizeNumber(result.confidence ?? result["Confidence"]),
    pageFound: normalizeBoolean(result.pageFound ?? result["Page Found"]),
    score: normalizeNumber(result.score ?? result.compositeScore ?? result["Score"]),
    total: normalizeNumber(result.total ?? result["Total"]),
    percent: normalizeNumber(result.percent ?? result["Percent"]),
    compositeComputed: normalizeBoolean(result.compositeComputed ?? result["Composite Computed"]),
    notes: result.notes || result["Notes"] || "",
    sectionScores: normalizeSectionScores(result.sectionScores ?? result["Section Scores"]),
    finalAnswers,
  };
}

function normalizeSectionScores(sectionScores) {
  if (!sectionScores || typeof sectionScores !== "object") {
    return null;
  }

  return Object.entries(sectionScores).map(([key, value]) => ({
    key,
    title: value?.title || startCase(key),
    rawScore: normalizeNumber(value?.rawScore),
    maxRaw: normalizeNumber(value?.maxRaw),
    scaleScore: normalizeNumber(value?.scaleScore),
    categoryScores: value?.categoryScores && typeof value.categoryScores === "object"
      ? Object.entries(value.categoryScores)
      : [],
  }));
}

function renderSectionScores(sectionScores) {
  sectionScoresGrid.innerHTML = "";

  if (!sectionScores || sectionScores.length === 0) {
    sectionScoresGrid.hidden = true;
    sectionScoresEmpty.hidden = false;
    return;
  }

  sectionScores.forEach((section) => {
    const card = document.createElement("article");
    card.className = "section-score-card";

    const header = document.createElement("div");
    header.className = "section-score-header";

    const label = document.createElement("span");
    label.className = "meta-label";
    label.textContent = section.title;
    header.append(label);

    const scale = document.createElement("strong");
    scale.textContent = section.scaleScore !== null ? `Scale ${section.scaleScore}` : "Scale -";
    header.append(scale);
    card.append(header);

    const raw = document.createElement("p");
    raw.className = "section-raw";
    raw.textContent = section.rawScore !== null && section.maxRaw !== null
      ? `Raw ${section.rawScore}/${section.maxRaw}`
      : "Raw -";
    card.append(raw);

    if (section.categoryScores.length > 0) {
      const categoryGrid = document.createElement("div");
      categoryGrid.className = "category-grid";

      section.categoryScores.forEach(([categoryName, categoryValue]) => {
        const item = document.createElement("div");
        item.className = "category-chip";

        const categoryLabel = document.createElement("span");
        categoryLabel.className = "meta-label";
        categoryLabel.textContent = categoryName;
        item.append(categoryLabel);

        const categoryScore = document.createElement("strong");
        categoryScore.textContent = `${categoryValue.correct}/${categoryValue.total}`;
        item.append(categoryScore);

        categoryGrid.append(item);
      });

      card.append(categoryGrid);
    }

    sectionScoresGrid.append(card);
  });

  sectionScoresEmpty.hidden = true;
  sectionScoresGrid.hidden = false;
}

function startCase(value) {
  return String(value)
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function parseAnswersValue(value) {
  if (!value) {
    return null;
  }

  if (typeof value === "object") {
    return value;
  }

  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return typeof parsed === "object" && parsed !== null ? parsed : null;
    } catch (error) {
      return null;
    }
  }

  return null;
}

function normalizeAnswers(answers) {
  return Object.entries(answers).sort((left, right) => compareQuestionKeys(left[0], right[0]));
}

function compareQuestionKeys(left, right) {
  const leftMatch = String(left).match(/^([A-Z]+)/i);
  const rightMatch = String(right).match(/^([A-Z]+)/i);
  const leftPrefix = leftMatch ? leftMatch[1] : "";
  const rightPrefix = rightMatch ? rightMatch[1] : "";

  if (leftPrefix !== rightPrefix) {
    return leftPrefix.localeCompare(rightPrefix, undefined, { sensitivity: "base" });
  }

  const leftNumber = extractQuestionNumber(left);
  const rightNumber = extractQuestionNumber(right);

  if (leftNumber !== null && rightNumber !== null && leftNumber !== rightNumber) {
    return leftNumber - rightNumber;
  }

  return left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" });
}

function extractQuestionNumber(value) {
  const match = String(value).match(/\d+/);
  return match ? Number(match[0]) : null;
}

function normalizeNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeBoolean(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  if (typeof value === "boolean") {
    return value;
  }

  if (typeof value === "string") {
    if (value.toLowerCase() === "true") {
      return true;
    }
    if (value.toLowerCase() === "false") {
      return false;
    }
  }

  return Boolean(value);
}

function answerState(answer) {
  const normalized = String(answer || "").toLowerCase();
  if (["blank", "multiple", "unclear"].includes(normalized)) {
    return normalized;
  }
  return "filled";
}

function buildResultStatusMessage(result) {
  const normalizedResult = normalizeResultPayload(result);
  const status = normalizedResult.finalStatus || "processed";
  const method = normalizedResult.finalMethod || "workflow";
  return `Status: ${status}. Method: ${method}.`;
}

function setStatus(message, tone) {
  statusBox.textContent = message;
  statusBox.className = `status-box status-${tone}`;
}

function formatBytes(bytes) {
  if (!bytes) {
    return "0 B";
  }

  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = 0;

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function truncate(value, maxLength) {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength - 3)}...`;
}
