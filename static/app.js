const questionInput = document.querySelector("#question");
const urlsInput = document.querySelector("#urls");
const submitButton = document.querySelector("#submit");
const statusBox = document.querySelector("#status");
const sourcesBox = document.querySelector("#sources");
const reportBox = document.querySelector("#report");

submitButton.addEventListener("click", async () => {
  const question = questionInput.value.trim();
  const urls = urlsInput.value
    .split("\n")
    .map((value) => value.trim())
    .filter(Boolean);

  if (question.length < 5 || urls.length < 2 || urls.length > 5) {
    statusBox.textContent = "请输入问题，并提供 2–5 个网址。";
    return;
  }

  submitButton.disabled = true;
  statusBox.textContent = "正在读取网页并比较，请稍候……";
  sourcesBox.textContent = "";
  reportBox.textContent = "";

  try {
    const response = await fetch("/api/compare", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question, urls}),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail)
      );
    }

    for (const source of data.sources) {
      const item = document.createElement("p");
      item.textContent = source.ok
        ? `成功：${source.final_url || source.url}（${source.elapsed_ms} ms）`
        : `失败：${source.url}（${source.error}）`;
      sourcesBox.appendChild(item);
    }

    reportBox.textContent = data.markdown;
    statusBox.textContent = "分析完成。";
  } catch (error) {
    statusBox.textContent = `分析失败：${error.message}`;
  } finally {
    submitButton.disabled = false;
  }
});