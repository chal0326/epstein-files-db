/**
 * DOJ Epstein Files URL Extractor
 *
 * INSTRUCTIONS:
 * 1. Open https://www.justice.gov/epstein/doj-disclosures/data-set-8-files in your browser
 * 2. Open browser console (F12 or Cmd+Option+J)
 * 3. Paste this entire script and press Enter
 * 4. Script will automatically navigate through ALL pages and collect URLs
 * 5. When done, it will download a text file with all URLs
 *
 * WHY THIS WORKS:
 * The DOJ/Akamai CDN blocks automated scripts but allows real browsers.
 * Running JavaScript in YOUR browser bypasses the blocking.
 */

(async function () {
  console.log("Starting DOJ File URL Extraction...");

  const allUrls = new Set();
  let currentPage = 0;
  let foundFiles = 0;

  // Create status display
  const statusDiv = document.createElement("div");
  statusDiv.style.cssText =
    "position:fixed;top:10px;right:10px;background:black;color:lime;padding:20px;z-index:99999;font-family:monospace;border:2px solid lime;";
  statusDiv.innerHTML =
    '<h3>URL Extraction Running...</h3><div id="extractStatus">Starting...</div>';
  document.body.appendChild(statusDiv);
  const statusText = document.getElementById("extractStatus");

  function updateStatus(msg) {
    console.log(msg);
    statusText.innerHTML += "<br>" + msg;
    statusDiv.scrollTop = statusDiv.scrollHeight;
  }

  async function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function extractUrlsFromCurrentPage() {
    // Find all PDF links on current page
    const links = document.querySelectorAll('a[href*=".pdf"]');
    let pageCount = 0;

    links.forEach((link) => {
      const url = link.href;
      if (url.includes("/epstein/files/") && url.endsWith(".pdf")) {
        allUrls.add(url);
        pageCount++;
      }
    });

    return pageCount;
  }

  async function hasNextPage() {
    // Check if "Next" button exists and is enabled
    const nextButton = document.querySelector('a[aria-label="Next page"]');
    return nextButton && !nextButton.classList.contains("disabled");
  }

  async function goToNextPage() {
    const nextButton = document.querySelector('a[aria-label="Next page"]');
    if (nextButton) {
      nextButton.click();
      return true;
    }
    return false;
  }

  // Main extraction loop
  while (true) {
    const pageUrls = await extractUrlsFromCurrentPage();
    foundFiles += pageUrls;
    currentPage++;

    updateStatus(
      `Page ${currentPage}: Found ${pageUrls} files (Total: ${allUrls.size} unique URLs)`,
    );

    if (!(await hasNextPage())) {
      updateStatus("✓ Reached last page!");
      break;
    }

    if (currentPage > 500) {
      updateStatus("⚠ Safety limit reached (500 pages)");
      break;
    }

    // Navigate to next page
    await goToNextPage();

    // Wait for page to load (adjust delay as needed)
    await sleep(2000);
  }

  // Download results as text file
  const urlList = Array.from(allUrls).sort().join("\n");
  const blob = new Blob([urlList], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "dataset8_urls.txt";
  a.click();

  updateStatus(`<br><strong>✓ DONE! Downloaded ${allUrls.size} URLs</strong>`);
  console.log("Complete! URLs saved to dataset8_urls.txt");
  console.log(
    `Found ${allUrls.size} unique file URLs across ${currentPage} pages`,
  );
})();
