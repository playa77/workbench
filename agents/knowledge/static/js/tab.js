/** Knowledge Base Tab Component
 *  Three-panel layout: KB list | Documents & Ingestion | Query interface
 */

(function () {
  Router.register("knowledge", renderKnowledgeTab);

  var state = {
    kbs: [],
    activeKbId: null,
    activeKb: null,
    documents: [],
    progressInterval: null,
    streamAbortController: null,
  };

  function renderKnowledgeTab(container) {
    container.innerHTML =
      '<div class="kb-layout">' +
      '<div class="kb-panel kb-panel-left" id="kb-left-panel"></div>' +
      '<div class="kb-panel kb-panel-center" id="kb-center-panel"></div>' +
      '<div class="kb-panel kb-panel-right" id="kb-right-panel"></div>' +
      '</div>';

    renderLeftPanel();
    loadKBs();
  }

  /* ---- Left Panel: KB List ---- */

  function renderLeftPanel() {
    var el = document.getElementById("kb-left-panel");
    el.innerHTML =
      '<h3 class="kb-panel-title">Knowledge Bases</h3>' +
      '<button class="btn btn-primary btn-sm" id="kb-new-btn" style="width:100%;margin-bottom:12px">' +
      'New Knowledge Base</button>' +
      '<div id="kb-new-form" style="display:none"></div>' +
      '<div id="kb-list"></div>';
    document.getElementById("kb-new-btn").addEventListener("click", toggleNewKbForm);
  }

  function toggleNewKbForm() {
    var form = document.getElementById("kb-new-form");
    if (form.style.display === "none") {
      form.style.display = "block";
      form.innerHTML =
        '<div class="kb-form-box">' +
        '<div class="form-group">' +
        '<label>Name</label>' +
        '<input class="form-input" id="kb-new-name" placeholder="My Knowledge Base" style="font-size:12px;padding:6px 10px" />' +
        '</div>' +
        '<div class="form-group">' +
        '<label>Description</label>' +
        '<input class="form-input" id="kb-new-desc" placeholder="Optional" style="font-size:12px;padding:6px 10px" />' +
        '</div>' +
        '<div style="display:flex;gap:8px">' +
        '<div class="form-group" style="flex:1">' +
        '<label>Chunk Size</label>' +
        '<input class="form-input" type="number" id="kb-new-chunk" value="1000" min="200" max="8000" style="font-size:12px;padding:6px 10px" />' +
        '</div>' +
        '<div class="form-group" style="flex:1">' +
        '<label>Overlap</label>' +
        '<input class="form-input" type="number" id="kb-new-overlap" value="200" min="0" max="2000" style="font-size:12px;padding:6px 10px" />' +
        '</div>' +
        '</div>' +
        '<div style="display:flex;gap:8px;margin-top:8px">' +
        '<button class="btn btn-primary btn-sm" id="kb-new-create">Create</button>' +
        '<button class="btn btn-secondary btn-sm" id="kb-new-cancel">Cancel</button>' +
        '</div>' +
        '<div id="kb-new-status" style="margin-top:8px;font-size:11px;color:var(--text-muted)"></div>' +
        '</div>';
      document.getElementById("kb-new-create").addEventListener("click", createKb);
      document.getElementById("kb-new-cancel").addEventListener("click", function () {
        document.getElementById("kb-new-form").style.display = "none";
      });
    } else {
      form.style.display = "none";
    }
  }

  async function loadKBs() {
    try {
      var resp = await fetch("/api/v1/agents/knowledge/kbs");
      var data = await resp.json();
      state.kbs = data.kbs || [];
      renderKbList();
    } catch (e) {
      document.getElementById("kb-list").innerHTML =
        '<p style="font-size:12px;color:var(--text-muted)">Failed to load</p>';
    }
  }

  function renderKbList() {
    var el = document.getElementById("kb-list");
    if (!state.kbs.length) {
      el.innerHTML =
        '<p style="font-size:12px;color:var(--text-muted);padding:8px">No knowledge bases yet</p>';
      return;
    }
    el.innerHTML = state.kbs
      .map(function (kb) {
        var active = state.activeKbId === kb.id ? " kb-item-active" : "";
        return (
          '<div class="kb-item' +
          active +
          '" data-kb-id="' +
          Utils.escapeHtml(kb.id) +
          '">' +
          '<div class="kb-item-name">' +
          Utils.escapeHtml(kb.name) +
          "</div>" +
          '<div class="kb-item-meta">' +
          (kb.document_count || 0) +
          " docs &middot; " +
          (kb.chunk_count || 0) +
          " chunks" +
          "</div>" +
          "</div>"
        );
      })
      .join("");
    el.querySelectorAll(".kb-item").forEach(function (item) {
      item.addEventListener("click", function () {
        selectKb(this.dataset.kbId);
      });
    });
  }

  function selectKb(kbId) {
    state.activeKbId = kbId;
    state.activeKb = state.kbs.find(function (k) {
      return k.id === kbId;
    });
    state.documents = [];
    renderKbList();
    renderCenterPanel();
    renderRightPanel();
  }

  async function createKb() {
    var name = document.getElementById("kb-new-name").value.trim();
    if (!name) return;
    var statusEl = document.getElementById("kb-new-status");
    statusEl.textContent = "Creating...";
    try {
      var resp = await fetch("/api/v1/agents/knowledge/kbs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name,
          description: document.getElementById("kb-new-desc").value.trim() || null,
          chunk_size: parseInt(document.getElementById("kb-new-chunk").value) || 1000,
          chunk_overlap: parseInt(document.getElementById("kb-new-overlap").value) || 200,
        }),
      });
      if (!resp.ok) {
        var err = await resp.json();
        throw new Error(err.detail || "Failed");
      }
      document.getElementById("kb-new-form").style.display = "none";
      await loadKBs();
    } catch (e) {
      statusEl.textContent = "Error: " + Utils.escapeHtml(e.message);
    }
  }

  /* ---- Center Panel: Documents & Ingestion ---- */

  function renderCenterPanel() {
    var el = document.getElementById("kb-center-panel");
    if (!state.activeKbId) {
      el.innerHTML =
        '<div class="kb-placeholder">Select or create a knowledge base</div>';
      return;
    }

    el.innerHTML =
      '<h3 class="kb-panel-title">Documents</h3>' +
      '<div class="kb-upload-zone" id="kb-upload-zone">' +
      '<div id="kb-upload-progress" class="kb-progress-bar" style="display:none"><div class="kb-progress-fill"></div></div>' +
      '<div id="kb-upload-text" style="text-align:center">Drop files here or click to browse<br><span style="font-size:11px;color:var(--text-muted)">Supports .txt, .md, .pdf</span></div>' +
      '<input type="file" id="kb-file-input" accept=".txt,.md,.pdf" style="display:none" />' +
      "</div>" +
      '<details class="kb-paste-section">' +
      '<summary class="kb-paste-summary">Paste text instead</summary>' +
      '<div class="form-group" style="margin-top:8px">' +
      '<input class="form-input" id="kb-paste-filename" placeholder="Filename (optional)" style="font-size:12px;padding:6px 10px;margin-bottom:8px" />' +
      '<textarea class="form-input" id="kb-paste-content" placeholder="Paste your text here..." style="min-height:120px;font-size:12px;padding:8px;resize:vertical" rows="6"></textarea>' +
      '<button class="btn btn-primary btn-sm" id="kb-paste-submit" style="margin-top:8px">Ingest Text</button>' +
      "</div>" +
      "</details>" +
      '<div id="kb-documents-list"></div>';

    setupUploadZone();
    setupPasteSubmit();
    loadDocuments();
  }

  function setupUploadZone() {
    var zone = document.getElementById("kb-upload-zone");
    var input = document.getElementById("kb-file-input");
    var progressContainer = document.getElementById("kb-upload-progress");
    var textEl = document.getElementById("kb-upload-text");

    zone.addEventListener("click", function () {
      input.click();
    });

    zone.addEventListener("dragover", function (e) {
      e.preventDefault();
      zone.classList.add("kb-upload-zone-dragover");
    });
    zone.addEventListener("dragleave", function () {
      zone.classList.remove("kb-upload-zone-dragover");
    });
    zone.addEventListener("drop", function (e) {
      e.preventDefault();
      zone.classList.remove("kb-upload-zone-dragover");
      if (e.dataTransfer.files.length) {
        handleFileUpload(e.dataTransfer.files[0]);
      }
    });

    input.addEventListener("change", function () {
      if (input.files.length) {
        handleFileUpload(input.files[0]);
      }
    });
  }

  async function handleFileUpload(file) {
    var textEl = document.getElementById("kb-upload-text");
    var progressContainer = document.getElementById("kb-upload-progress");
    var progressFill = progressContainer.querySelector(".kb-progress-fill");

    textEl.textContent = "Uploading " + Utils.escapeHtml(file.name) + "...";
    progressContainer.style.display = "block";
    progressFill.style.width = "0%";

    try {
      var form = new FormData();
      form.append("file", file);

      var resp = await fetch(
        "/api/v1/agents/knowledge/kbs/" + encodeURIComponent(state.activeKbId) + "/upload",
        { method: "POST", body: form }
      );
      if (!resp.ok) {
        var err = await resp.json();
        throw new Error(err.detail || "Upload failed");
      }

      startProgressPolling(progressFill, textEl);
      await loadDocuments();
      await loadKBs();
    } catch (e) {
      textEl.textContent = "Error: " + Utils.escapeHtml(e.message);
      progressContainer.style.display = "none";
    }
  }

  function startProgressPolling(fillEl, textEl) {
    if (state.progressInterval) clearInterval(state.progressInterval);
    state.progressInterval = setInterval(async function () {
      try {
        var resp = await fetch(
          "/api/v1/agents/knowledge/kbs/" +
            encodeURIComponent(state.activeKbId) +
            "/ingestion-progress"
        );
        var data = await resp.json();
        if (!data.active) {
          clearInterval(state.progressInterval);
          state.progressInterval = null;
          fillEl.style.width = "100%";
          textEl.textContent = "Ingestion complete";
          var pc = document.getElementById("kb-upload-progress");
          if (pc) setTimeout(function () { pc.style.display = "none"; }, 2000);
          return;
        }
        var pct = data.total > 0 ? Math.round((data.processed / data.total) * 100) : 0;
        fillEl.style.width = pct + "%";
        textEl.textContent =
          "Embedding chunks... " + data.processed + " / " + data.total;
      } catch (e) {
        /* poll silently */
      }
    }, 2000);
  }

  function setupPasteSubmit() {
    var btn = document.getElementById("kb-paste-submit");
    if (!btn) return;
    btn.addEventListener("click", async function () {
      var content = document.getElementById("kb-paste-content").value.trim();
      var filename = document.getElementById("kb-paste-filename").value.trim();
      if (!content) return;

      btn.disabled = true;
      btn.textContent = "Ingesting...";

      try {
        var resp = await fetch(
          "/api/v1/agents/knowledge/kbs/" +
            encodeURIComponent(state.activeKbId) +
            "/upload-text",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              content: content,
              filename: filename || null,
            }),
          }
        );
        if (!resp.ok) {
          var err = await resp.json();
          throw new Error(err.detail || "Failed");
        }
        document.getElementById("kb-paste-content").value = "";
        document.getElementById("kb-paste-filename").value = "";
        await loadDocuments();
        await loadKBs();
      } catch (e) {
        btn.textContent = "Error: " + Utils.escapeHtml(e.message);
        setTimeout(function () {
          btn.textContent = "Ingest Text";
          btn.disabled = false;
        }, 2000);
        return;
      }
      btn.textContent = "Ingest Text";
      btn.disabled = false;
    });
  }

  async function loadDocuments() {
    if (!state.activeKbId) return;
    try {
      var resp = await fetch(
        "/api/v1/agents/knowledge/kbs/" +
          encodeURIComponent(state.activeKbId) +
          "/documents"
      );
      var data = await resp.json();
      state.documents = data.documents || [];
      renderDocumentsList();
    } catch (e) {
      /* silently fail */
    }
  }

  function renderDocumentsList() {
    var el = document.getElementById("kb-documents-list");
    if (!el) return;
    if (!state.documents.length) {
      el.innerHTML =
        '<p style="font-size:12px;color:var(--text-muted);padding:8px">No documents yet</p>';
      return;
    }
    el.innerHTML =
      '<div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin:12px 0 4px">' +
      state.documents.length +
      " document(s)" +
      "</div>" +
      state.documents
        .map(function (doc) {
          var statusClass = "kb-doc-" + doc.status;
          return (
            '<div class="kb-doc-item" data-doc-id="' +
            Utils.escapeHtml(doc.id) +
            '">' +
            '<div class="kb-doc-header">' +
            '<span class="kb-doc-name">' +
            Utils.escapeHtml(doc.filename) +
            "</span>" +
            '<span class="kb-doc-status ' +
            statusClass +
            '">' +
            Utils.escapeHtml(doc.status) +
            "</span>" +
            '<button class="btn btn-danger btn-xs kb-doc-delete" data-doc-id="' +
            Utils.escapeHtml(doc.id) +
            '" title="Delete document">x</button>' +
            "</div>" +
            '<div class="kb-doc-meta">' +
            (doc.chunk_count || 0) +
            " chunks" +
            (doc.error_message
              ? ' &middot; <span style="color:var(--danger)">' +
                Utils.escapeHtml(doc.error_message) +
                "</span>"
              : "") +
            "</div>" +
            "</div>"
          );
        })
        .join("");

    el.querySelectorAll(".kb-doc-delete").forEach(function (btn) {
      btn.addEventListener("click", async function (e) {
        e.stopPropagation();
        var docId = btn.dataset.docId;
        await deleteDocument(docId);
      });
    });
  }

  async function deleteDocument(docId) {
    try {
      var resp = await fetch(
        "/api/v1/agents/knowledge/kbs/" +
          encodeURIComponent(state.activeKbId) +
          "/documents/" +
          encodeURIComponent(docId),
        { method: "DELETE" }
      );
      if (!resp.ok) throw new Error("Failed");
      await loadDocuments();
      await loadKBs();
    } catch (e) {
      /* silently fail */
    }
  }

  /* ---- Right Panel: Query ---- */

  function renderRightPanel() {
    var el = document.getElementById("kb-right-panel");
    if (!state.activeKbId) {
      el.innerHTML =
        '<div class="kb-placeholder">Select a knowledge base to query</div>';
      return;
    }

    el.innerHTML =
      '<h3 class="kb-panel-title">Query</h3>' +
      '<div id="kb-query-messages" style="flex:1;overflow-y:auto;margin-bottom:12px;padding:8px 0"></div>' +
      '<div style="display:flex;gap:8px">' +
      '<input class="form-input" id="kb-query-input" placeholder="Ask a question about your documents..." style="flex:1;font-size:14px" onkeydown="if(event.key==\'Enter\')window.kbQuerySend()" />' +
      '<button class="btn btn-primary" onclick="window.kbQuerySend()">Send</button>' +
      "</div>" +
      '<div style="margin-top:6px;font-size:11px;color:var(--text-muted)">Responses are based on your ingested documents</div>';

    document.getElementById("kb-query-messages").innerHTML =
      '<div style="text-align:center;color:var(--text-muted);padding:20px">Ask a question to search your documents</div>';

    window.kbQuerySend = kbQuerySend;
  }

  async function kbQuerySend() {
    var input = document.getElementById("kb-query-input");
    var question = input.value.trim();
    if (!question) return;
    input.value = "";

    var msgs = document.getElementById("kb-query-messages");
    if (msgs.querySelector('div[style*="text-align:center"]')) msgs.innerHTML = "";

    addQueryMessage("user", question);

    if (state.streamAbortController) {
      state.streamAbortController.abort();
    }
    state.streamAbortController = new AbortController();

    var responseDiv = addQueryMessage("assistant", "");
    var responseText = "";

    try {
      var resp = await fetch(
        "/api/v1/agents/knowledge/kbs/" +
          encodeURIComponent(state.activeKbId) +
          "/query",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: question, top_k: 5 }),
          signal: state.streamAbortController.signal,
        }
      );

      if (!resp.ok) {
        var errText = await resp.text();
        try {
          var errJson = JSON.parse(errText);
          throw new Error(errJson.detail || "Query error");
        } catch (parseErr) {
          throw new Error("Query error: " + resp.status);
        }
      }

      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";
      var sources = null;

      while (true) {
        var result = await reader.read();
        if (result.done) break;
        buffer += decoder.decode(result.value, { stream: true });

        var lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (var i = 0; i < lines.length; i++) {
          var line = lines[i].trim();
          if (!line) continue;

          if (line.startsWith("event: chunk")) {
            var dataIdx = i + 1;
            while (dataIdx < lines.length && !lines[dataIdx].startsWith("data: ")) {
              dataIdx++;
            }
            if (dataIdx < lines.length) {
              var dataLine = lines[dataIdx];
              try {
                var chunkData = JSON.parse(dataLine.substring(6));
                responseText += chunkData.content;
                var contentEl = responseDiv.querySelector(".kb-msg-content");
                if (contentEl) {
                  contentEl.textContent = responseText;
                  msgs.scrollTop = msgs.scrollHeight;
                }
              } catch (e) {}
              i = dataIdx;
            }
          } else if (line.startsWith("event: sources")) {
            var si = i + 1;
            while (si < lines.length && !lines[si].startsWith("data: ")) si++;
            if (si < lines.length) {
              try {
                sources = JSON.parse(lines[si].substring(6));
              } catch (e) {}
              i = si;
            }
          }
        }
      }

      if (sources && sources.sources && sources.sources.length) {
        var srcHtml =
          '<div class="kb-sources"><div class="kb-sources-title">Sources</div>';
        sources.sources.forEach(function (s) {
          srcHtml +=
            '<div class="kb-source-item"><span class="kb-source-filename">' +
            Utils.escapeHtml(s.filename) +
            "</span>" +
            (s.score !== undefined
              ? ' <span class="kb-source-score">(' +
                (Math.round(s.score * 1000) / 1000).toFixed(3) +
                ")</span>"
              : "") +
            '<div class="kb-source-text">' +
            Utils.escapeHtml(s.text) +
            "</div></div>";
        });
        srcHtml += "</div>";
        responseDiv.innerHTML =
          '<div class="kb-msg-label">Assistant</div>' +
          '<div class="kb-msg-content">' +
          Utils.escapeHtml(responseText) +
          "</div>" +
          srcHtml;
      }
    } catch (e) {
      if (e.name !== "AbortError") {
        addQueryMessage("assistant", "Error: " + Utils.escapeHtml(e.message));
      }
    }
    state.streamAbortController = null;
  }

  function addQueryMessage(role, content) {
    var msgs = document.getElementById("kb-query-messages");
    if (!msgs) return;
    var div = document.createElement("div");
    div.className = "kb-msg kb-msg-" + role;
    div.innerHTML =
      '<div class="kb-msg-label">' +
      (role === "user" ? "You" : "Assistant") +
      "</div>" +
      '<div class="kb-msg-content">' +
      Utils.escapeHtml(content) +
      "</div>";
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    return div;
  }

  /* ---- Utils ---- */

  window.Utils = window.Utils || {};
  if (!window.Utils.escapeHtml) {
    window.Utils.escapeHtml = function (str) {
      if (!str) return "";
      return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    };
  }
})();
