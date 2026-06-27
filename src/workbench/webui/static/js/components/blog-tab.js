/** Blog / Publishing Hub Tab Component
 *  Manages blog posts: list, create, edit, delete, and view git history.
 *  Communicates with /api/v1/blog/posts REST endpoints.
 *  Version: 1.0.0 | 2026-06-23
 */

(function () {
  Router.register("blog", renderBlogTab);

  /* ---- State ---- */
  var state = {
    posts: [],
    activePost: null,   // full post object (or null for new)
    editing: false,     // true when editor is open
    loading: false,
  };

  /* ---- API helpers ---- */

  /** Generic blog API fetch with auth, Content-Type handling, and error extraction. */
  function blogAPI(method, path, body) {
    var opts = { method: method, headers: {} };
    // Attach auth token if available
    try {
      var apiKey = (API && API.getApiKey) ? API.getApiKey() : '';
      if (apiKey) opts.headers['Authorization'] = 'Bearer ' + apiKey;
    } catch (_e) {}
    if (body && !(body instanceof FormData)) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    } else if (body instanceof FormData) {
      opts.body = body;
    }
    return fetch(path, opts).then(function (r) {
      if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || r.statusText); });
      return r.json();
    });
  }

  /* ---- Main render ---- */

  function renderBlogTab(container) {
    container.innerHTML =
      '<div class="blog-layout">' +
      '  <div class="blog-panel-left" id="blog-left-panel"></div>' +
      '  <div class="blog-panel-right" id="blog-right-panel"></div>' +
      '</div>' +
      '<div id="blog-inspection-overlay" class="blog-inspection-overlay" style="display:none"></div>';

    renderLeftPanel();
    loadPosts();
  }

  /* ---- Left Panel (post list) ---- */

  function renderLeftPanel() {
    var panel = document.getElementById('blog-left-panel');
    if (!panel) return;
    panel.innerHTML =
      '<div class="blog-left-header">' +
      '  <button class="btn btn-primary btn-sm" id="btn-blog-new" data-tooltip="Create a new blog post. Choose between Markdown, HTML, or PDF format." data-help-page="/static/help/blog.html#new-document">+ New Document</button>' +
      '</div>' +
      '<div class="blog-left-list" id="blog-post-list"></div>';

    document.getElementById('btn-blog-new').addEventListener('click', function () {
      newDocument();
    });
  }

  function renderPostList() {
    var list = document.getElementById('blog-post-list');
    if (!list) return;

    if (state.posts.length === 0) {
      list.innerHTML = '<div class="blog-empty-state">No documents yet. Click "New Document" to create one.</div>';
      return;
    }

    list.innerHTML = state.posts.map(function (p) {
      var formatBadge = formatLabel(p.format);
      var statusHtml = p.is_published
        ? '<span class="blog-status published"><span class="blog-dot published-dot"></span> Published</span>'
        : '<span class="blog-status draft"><span class="blog-dot draft-dot"></span> Draft</span>';
      var dateHtml = p.updated_at
        ? '<span class="blog-date">' + p.updated_at.split('T')[0] + '</span>'
        : '';
      var activeClass = state.activePost && state.activePost.id === p.id ? ' blog-post-active' : '';
      return '<div class="blog-post-entry' + activeClass + '" data-post-id="' + p.id + '" data-tooltip="Click to edit this blog post." data-help-page="/static/help/blog.html#post-list">' +
        '<div class="blog-post-title-row">' +
        '  <span class="blog-post-title">' + Utils.escapeHtml(p.title || 'Untitled') + '</span>' +
        '  ' + formatBadge +
        '</div>' +
        '<div class="blog-post-meta">' +
        '  ' + statusHtml +
        '  ' + dateHtml +
        '</div>' +
        '</div>';
    }).join('');

    list.querySelectorAll('.blog-post-entry').forEach(function (el) {
      el.addEventListener('click', function () {
        var id = el.dataset.postId;
        selectPost(id);
      });
    });
  }

  function formatLabel(format) {
    format = (format || 'md').toLowerCase();
    var label = format === 'md' ? 'MD' : format === 'html' ? 'HTML' : format === 'pdf' ? 'PDF' : format.toUpperCase();
    var cls = 'blog-format-badge ';
    if (format === 'md') cls += 'badge-md';
    else if (format === 'html') cls += 'badge-html';
    else if (format === 'pdf') cls += 'badge-pdf';
    else cls += 'badge-md';
    return '<span class="' + cls + '">' + label + '</span>';
  }

  /* ---- Data loading ---- */

  function loadPosts() {
    state.loading = true;
    blogAPI('GET', '/api/v1/blog/posts').then(function (posts) {
      state.posts = posts || [];
      state.loading = false;
      renderPostList();
      // If we have an active post that still exists, keep editor open; else clear
      if (state.activePost) {
        var stillExists = state.posts.some(function (p) { return p.id === state.activePost.id; });
        if (!stillExists) {
          clearEditor();
        } else {
          // Reload the active post
          loadPostDetail(state.activePost.id);
        }
      }
    }).catch(function (err) {
      state.loading = false;
      var list = document.getElementById('blog-post-list');
      if (list) list.innerHTML = '<div class="blog-empty-state">Failed to load posts: ' + Utils.escapeHtml(err.message) + '</div>';
    });
  }

  function loadPostDetail(id) {
    blogAPI('GET', '/api/v1/blog/posts/' + id).then(function (post) {
      state.activePost = post;
      state.editing = true;
      renderEditor();
    }).catch(function (err) {
      Utils.showToast('Failed to load post: ' + err.message, 'error');
    });
  }

  function selectPost(id) {
    // Deselect previously active visual
    var list = document.getElementById('blog-post-list');
    if (list) {
      list.querySelectorAll('.blog-post-active').forEach(function (el) { el.classList.remove('blog-post-active'); });
      var entry = list.querySelector('[data-post-id="' + id + '"]');
      if (entry) entry.classList.add('blog-post-active');
    }
    loadPostDetail(id);
  }

  function newDocument() {
    state.activePost = null;
    state.editing = true;
    // Clear active highlight
    var list = document.getElementById('blog-post-list');
    if (list) list.querySelectorAll('.blog-post-active').forEach(function (el) { el.classList.remove('blog-post-active'); });
    renderEditor();
  }

  function clearEditor() {
    state.activePost = null;
    state.editing = false;
    var rightPanel = document.getElementById('blog-right-panel');
    if (rightPanel) {
      rightPanel.innerHTML =
        '<div class="blog-editor-empty">' +
        '  <p>Select a document from the list or create a new one.</p>' +
        '</div>';
    }
  }

  /* ---- Right Panel (editor) ---- */

  function renderEditor() {
    var panel = document.getElementById('blog-right-panel');
    if (!panel) return;
    var post = state.activePost;
    var isNew = !post;
    var title = isNew ? '' : (post.title || '');
    var format = isNew ? 'md' : (post.format || 'md').toLowerCase();
    var content = isNew ? '' : (post.content || '');
    var comment = isNew ? '' : (post.comment || '');
    var published = isNew ? false : !!post.is_published;

    panel.innerHTML =
      '<div class="blog-editor">' +
      '  <div class="blog-editor-header">' +
      '    <h3>' + (isNew ? 'New Document' : 'Edit Document') + '</h3>' +
      '    <div class="blog-editor-actions">' +
      (isNew ? '' : '<button class="btn btn-secondary btn-sm" id="btn-blog-history" data-tooltip="Open the version history overlay showing git commits with timestamps and messages." data-help-page="/static/help/blog.html#history">History</button>') +
      '      <button class="btn btn-secondary btn-sm" id="btn-blog-cancel" data-tooltip="Discard unsaved changes and return to the post list." data-help-page="/static/help/blog.html#save-delete">Cancel</button>' +
      '    </div>' +
      '  </div>' +

      '  <div class="blog-editor-form">' +
      /* Title */
      '    <div class="form-group">' +
      '      <label>Title</label>' +
      '      <input class="form-input" id="blog-field-title" type="text" value="' + Utils.escapeHtml(title) + '" placeholder="Post title" data-tooltip="The document title. Auto-generates a URL slug for your public blog page." data-help-page="/static/help/blog.html#new-document" />' +
      '    </div>' +

      /* Format */
      '    <div class="form-group">' +
      '      <label>Format</label>' +
      '      <select class="form-input" id="blog-field-format" data-tooltip="Document format: Markdown (rendered to HTML), Raw HTML, or PDF (upload only)." data-help-page="/static/help/blog.html#new-document">' +
      '        <option value="md"' + (format === 'md' ? ' selected' : '') + '>Markdown</option>' +
      '        <option value="html"' + (format === 'html' ? ' selected' : '') + '>HTML</option>' +
      '        <option value="pdf"' + (format === 'pdf' ? ' selected' : '') + '>PDF</option>' +
      '      </select>' +
      '    </div>' +

      /* File upload + drag area */
      '    <div class="form-group">' +
      '      <label>File Upload <span style="font-size:11px;color:var(--text-muted)">(optional — drag a file or click to browse)</span></label>' +
      '      <div class="blog-file-upload" id="blog-file-upload-area" data-tooltip="Drag and drop a file or click to browse. Supported: .md, .html, .pdf. Uploaded content populates automatically." data-help-page="/static/help/blog.html#file-upload">' +
      '        <div class="blog-file-dropzone" id="blog-file-dropzone">' +
      '          <span id="blog-file-label">Drop a file here or click to browse</span>' +
      '          <input type="file" id="blog-file-input" style="display:none" />' +
      '        </div>' +
      '        <div id="blog-file-info" class="blog-file-info" style="display:none"></div>' +
      '      </div>' +
      '    </div>' +

      /* Content textarea */
      '    <div class="form-group">' +
      '      <label>Content <span style="font-size:11px;color:var(--text-muted)">(inline — used when no file is uploaded)</span></label>' +
      '      <textarea class="form-input blog-content-textarea" id="blog-field-content" placeholder="Write your content here..." data-tooltip="The main document body. Write in your chosen format — Markdown is rendered on the public page." data-help-page="/static/help/blog.html#new-document"' +
      '        style="min-height:300px;font-family:var(--font-mono, monospace);font-size:13px;line-height:1.5;resize:vertical">' + Utils.escapeHtml(content) + '</textarea>' +
      '    </div>' +

      /* Comment */
      '    <div class="form-group">' +
      '      <label>Comment <span style="font-size:11px;color:var(--text-muted)">(markdown supported, max 2048 chars)</span></label>' +
      '      <textarea class="form-input" id="blog-field-comment" placeholder="Commit message / description..." maxlength="2048" data-tooltip="Optional commit message describing this change. Visible in version history inspection (max 2048 chars)." data-help-page="/static/help/blog.html#new-document"' +
      '        style="min-height:60px;resize:vertical">' + Utils.escapeHtml(comment) + '</textarea>' +
      '      <div style="display:flex;justify-content:flex-end;margin-top:2px">' +
      '        <span id="blog-comment-counter" style="font-size:11px;color:var(--text-muted)">0 / 2048</span>' +
      '      </div>' +
      '    </div>' +

      /* Published toggle */
      '    <div class="form-group" style="flex-direction:row;align-items:center;gap:12px">' +
      '      <label style="margin-bottom:0">Published</label>' +
      '      <label class="toggle">' +
      '        <input type="checkbox" id="blog-field-published" data-tooltip="Make this document visible on your public blog page at /blog/your-username." data-help-page="/static/help/blog.html#public-blog"' + (published ? ' checked' : '') + ' />' +
      '        <span class="toggle-switch"></span>' +
      '      </label>' +
      '    </div>' +

      /* Action buttons */
      '    <div class="blog-editor-footer" style="display:flex;gap:8px;margin-top:16px;padding-top:16px;border-top:1px solid var(--border-color)">' +
      '      <button class="btn btn-primary" id="btn-blog-save" data-tooltip="Save the document. Commits to git version history and updates the public page if published." data-help-page="/static/help/blog.html#save-delete">Save</button>' +
      (isNew ? '' : '<button class="btn btn-danger" id="btn-blog-delete" data-tooltip="Permanently delete this document and its git history. This cannot be undone." data-help-page="/static/help/blog.html#save-delete">Delete</button>') +
      '    </div>' +

      '    <div id="blog-editor-status" style="margin-top:8px;font-size:12px;color:var(--danger)"></div>' +
      '  </div>' +
      '</div>';

    /* ── Wire up events ── */

    // File upload dropzone
    var dropzone = document.getElementById('blog-file-dropzone');
    var fileInput = document.getElementById('blog-file-input');
    if (dropzone && fileInput) {
      dropzone.addEventListener('click', function () { fileInput.click(); });

      dropzone.addEventListener('dragover', function (e) {
        e.preventDefault();
        dropzone.classList.add('blog-dropzone-active');
      });
      dropzone.addEventListener('dragleave', function () {
        dropzone.classList.remove('blog-dropzone-active');
      });
      dropzone.addEventListener('drop', function (e) {
        e.preventDefault();
        dropzone.classList.remove('blog-dropzone-active');
        if (e.dataTransfer.files.length > 0) {
          fileInput.files = e.dataTransfer.files;
          handleFileSelected(e.dataTransfer.files[0]);
        }
      });

      fileInput.addEventListener('change', function () {
        if (fileInput.files.length > 0) {
          handleFileSelected(fileInput.files[0]);
        }
      });
    }

    // Comment character counter
    var commentField = document.getElementById('blog-field-comment');
    if (commentField) {
      updateCommentCounter();
      commentField.addEventListener('input', updateCommentCounter);
    }

    // Cancel button
    document.getElementById('btn-blog-cancel').addEventListener('click', function () {
      clearEditor();
    });

    // Save button
    document.getElementById('btn-blog-save').addEventListener('click', function () {
      savePost(this);
    });

    // Delete button
    var deleteBtn = document.getElementById('btn-blog-delete');
    if (deleteBtn) {
      deleteBtn.addEventListener('click', function () {
        deletePost(this);
      });
    }

    // History button
    var historyBtn = document.getElementById('btn-blog-history');
    if (historyBtn) {
      historyBtn.addEventListener('click', function () {
        if (state.activePost) showInspection(state.activePost.id);
      });
    }
  }

  function handleFileSelected(file) {
    var label = document.getElementById('blog-file-label');
    var info = document.getElementById('blog-file-info');
    var dropzone = document.getElementById('blog-file-dropzone');
    if (label && info && dropzone) {
      label.textContent = file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB) selected';
      info.style.display = 'block';
      info.innerHTML = '<span style="font-size:12px;color:var(--text-secondary)">File: ' + Utils.escapeHtml(file.name) + '</span>' +
        '<button class="btn btn-sm btn-secondary" id="btn-blog-clear-file" style="margin-left:8px">Remove</button>';
      document.getElementById('btn-blog-clear-file').addEventListener('click', function () {
        clearFileSelection();
      });
    }
    // Auto-detect format from extension
    var ext = file.name.split('.').pop().toLowerCase();
    var formatSelect = document.getElementById('blog-field-format');
    if (formatSelect && (ext === 'md' || ext === 'markdown')) formatSelect.value = 'md';
    else if (formatSelect && ext === 'html') formatSelect.value = 'html';
    else if (formatSelect && ext === 'pdf') formatSelect.value = 'pdf';
    // Store file reference for later use during save
    state._pendingFile = file;
  }

  function clearFileSelection() {
    state._pendingFile = null;
    var fileInput = document.getElementById('blog-file-input');
    var label = document.getElementById('blog-file-label');
    var info = document.getElementById('blog-file-info');
    if (fileInput) fileInput.value = '';
    if (label) label.textContent = 'Drop a file here or click to browse';
    if (info) { info.style.display = 'none'; info.innerHTML = ''; }
  }

  function updateCommentCounter() {
    var el = document.getElementById('blog-field-comment');
    var counter = document.getElementById('blog-comment-counter');
    if (el && counter) {
      var len = el.value.length;
      counter.textContent = len + ' / 2048';
      if (len > 2000) counter.style.color = 'var(--danger)';
      else counter.style.color = 'var(--text-muted)';
    }
  }

  /* ---- Save logic ---- */

  function savePost(btn) {
    var title = document.getElementById('blog-field-title').value.trim();
    var format = document.getElementById('blog-field-format').value;
    var comment = document.getElementById('blog-field-comment').value.trim() || '';
    var published = document.getElementById('blog-field-published').checked;
    var statusDiv = document.getElementById('blog-editor-status');
    if (statusDiv) statusDiv.textContent = '';

    if (!title) {
      if (statusDiv) statusDiv.textContent = 'Title is required.';
      return;
    }

    Utils.setButtonLoading(btn, 'Saving...');

    var isNew = !state.activePost;

    if (isNew) {
      // POST with multipart FormData
      var formData = new FormData();
      formData.append('title', title);
      formData.append('format', format);
      formData.append('comment', comment);
      formData.append('is_published', published ? 'true' : 'false');

      if (state._pendingFile) {
        formData.append('file', state._pendingFile);
      } else {
        var content = document.getElementById('blog-field-content').value;
        formData.append('content', content);
      }

      blogAPI('POST', '/api/v1/blog/posts', formData).then(function (post) {
        Utils.resetButton(btn);
        Utils.showToast('Document created', 'success');
        clearFileSelection();
        loadPosts();
      }).catch(function (err) {
        Utils.resetButton(btn);
        if (statusDiv) statusDiv.textContent = 'Error: ' + err.message;
        Utils.showToast('Failed to create: ' + err.message, 'error');
      });
    } else {
      // PUT with JSON
      var data = {
        title: title,
        format: format,
        comment: comment,
        is_published: published,
      };
      var content = document.getElementById('blog-field-content').value;
      if (content) data.content = content;

      blogAPI('PUT', '/api/v1/blog/posts/' + state.activePost.id, data).then(function (post) {
        Utils.resetButton(btn);
        Utils.showToast('Document saved', 'success');
        loadPosts();
      }).catch(function (err) {
        Utils.resetButton(btn);
        if (statusDiv) statusDiv.textContent = 'Error: ' + err.message;
        Utils.showToast('Failed to save: ' + err.message, 'error');
      });
    }
  }

  /* ---- Delete logic ---- */

  function deletePost(btn) {
    if (!state.activePost) return;
    if (!confirm('Delete "' + (state.activePost.title || 'Untitled') + '"? This cannot be undone.')) return;

    var statusDiv = document.getElementById('blog-editor-status');
    Utils.setButtonLoading(btn, 'Deleting...');

    blogAPI('DELETE', '/api/v1/blog/posts/' + state.activePost.id).then(function () {
      Utils.showToast('Document deleted', 'info');
      state.activePost = null;
      state.editing = false;
      loadPosts();
    }).catch(function (err) {
      Utils.resetButton(btn);
      if (statusDiv) statusDiv.textContent = 'Error: ' + err.message;
      Utils.showToast('Failed to delete: ' + err.message, 'error');
    });
  }

  /* ---- Inspection mode (History overlay) ---- */

  function showInspection(postId) {
    var overlay = document.getElementById('blog-inspection-overlay');
    if (!overlay) return;

    overlay.style.display = 'flex';
    overlay.innerHTML =
      '<div class="blog-inspection-panel">' +
      '  <div class="blog-inspection-header">' +
      '    <h3>File History</h3>' +
      '    <button class="btn btn-secondary btn-sm" id="btn-inspection-close" data-tooltip="Close the version history inspection and return to editing." data-help-page="/static/help/blog.html#history">Close</button>' +
      '  </div>' +
      '  <div class="blog-inspection-body" id="blog-inspection-body">' +
      '    <div class="spinner" style="margin:40px auto"></div>' +
      '  </div>' +
      '</div>';

    document.getElementById('btn-inspection-close').addEventListener('click', function () {
      overlay.style.display = 'none';
    });
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) overlay.style.display = 'none';
    });

    // Load history
    blogAPI('GET', '/api/v1/blog/posts/' + postId + '/history').then(function (data) {
      var filename = data.filename || '';
      var commits = data.commits || [];
      var body = document.getElementById('blog-inspection-body');

      if (commits.length === 0) {
        body.innerHTML = '<div style="text-align:center;padding:32px;color:var(--text-muted)">No history available for this file.</div>';
        return;
      }

      var html = '';
      if (filename) {
        html += '<div style="font-size:12px;color:var(--text-secondary);margin-bottom:12px;padding:8px;background:var(--bg-hover);border-radius:var(--radius-sm)">' +
          'File: <code style="font-family:var(--font-mono);font-size:12px">' + Utils.escapeHtml(filename) + '</code></div>';
      }
      html += '<div class="blog-commit-list">' +
        commits.map(function (c) {
          var shortHash = c.hash ? c.hash.substring(0, 8) : '';
          var date = c.date ? c.date.split('T')[0] : '';
          var msg = c.message || '';
          return '<div class="blog-commit-entry" data-hash="' + Utils.escapeHtml(c.hash) + '" data-filename="' + Utils.escapeHtml(filename) + '">' +
            '<div class="blog-commit-hash">' + Utils.escapeHtml(shortHash) + '</div>' +
            '<div class="blog-commit-date">' + Utils.escapeHtml(date) + '</div>' +
            '<div class="blog-commit-msg">' + Utils.escapeHtml(msg) + '</div>' +
            '</div>';
        }).join('') +
        '</div>' +
        '<div id="blog-commit-content" style="display:none;margin-top:16px"></div>';

      body.innerHTML = html;

      body.querySelectorAll('.blog-commit-entry').forEach(function (el) {
        el.addEventListener('click', function () {
          var hash = el.dataset.hash;
          loadCommitContent(postId, hash, filename);
          // Highlight selected
          body.querySelectorAll('.blog-commit-entry').forEach(function (e) { e.classList.remove('commit-selected'); });
          el.classList.add('commit-selected');
        });
      });
    }).catch(function (err) {
      var body = document.getElementById('blog-inspection-body');
      if (body) body.innerHTML = '<div style="text-align:center;padding:32px;color:var(--danger)">Failed to load history: ' + Utils.escapeHtml(err.message) + '</div>';
    });
  }

  function loadCommitContent(postId, hash, filename) {
    var contentDiv = document.getElementById('blog-commit-content');
    if (!contentDiv) return;
    contentDiv.style.display = 'block';
    contentDiv.innerHTML = '<div class="spinner" style="margin:20px auto"></div>';

    blogAPI('GET', '/api/v1/blog/posts/' + postId + '/history/' + hash).then(function (data) {
      var commitContent = data.content || '';
      contentDiv.innerHTML =
        '<div class="blog-commit-content-header">' +
        '  <span style="font-size:12px;font-weight:600;color:var(--text-secondary)">Content at ' + Utils.escapeHtml(data.commit_hash ? data.commit_hash.substring(0, 8) : hash.substring(0, 8)) + '</span>' +
        '</div>' +
        '<pre class="blog-commit-content-pre"><code>' + Utils.escapeHtml(commitContent) + '</code></pre>';
    }).catch(function (err) {
      contentDiv.innerHTML = '<div style="color:var(--danger);font-size:12px">Failed to load content: ' + Utils.escapeHtml(err.message) + '</div>';
    });
  }

  /* ---- CSS styles (injected once) ---- */

  (function injectBlogStyles() {
    if (document.getElementById('blog-tab-styles')) return;
    var style = document.createElement('style');
    style.id = 'blog-tab-styles';
    style.textContent = [
      /* Layout */
      '.blog-layout { display:flex; height:calc(100vh - 120px); gap:16px; }',
      '.blog-panel-left { width:280px; flex-shrink:0; display:flex; flex-direction:column; border:1px solid var(--border-color); border-radius:var(--radius); background:var(--bg-card); overflow:hidden; }',
      '.blog-panel-right { flex:1; overflow-y:auto; border:1px solid var(--border-color); border-radius:var(--radius); background:var(--bg-card); }',

      /* Left panel header */
      '.blog-left-header { padding:12px; border-bottom:1px solid var(--border-color); flex-shrink:0; }',
      '.blog-left-header .btn { width:100%; }',

      /* Post list */
      '.blog-left-list { flex:1; overflow-y:auto; padding:4px 0; }',
      '.blog-empty-state { padding:32px 16px; text-align:center; color:var(--text-muted); font-size:13px; }',

      '.blog-post-entry { padding:10px 12px; border-bottom:1px solid var(--border-color); cursor:pointer; transition:background 0.15s; }',
      '.blog-post-entry:hover { background:var(--bg-hover); }',
      '.blog-post-active { background:var(--accent-bg) !important; border-left:3px solid var(--accent); padding-left:9px; }',

      '.blog-post-title-row { display:flex; align-items:center; gap:6px; margin-bottom:4px; }',
      '.blog-post-title { font-size:13px; font-weight:600; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }',

      '.blog-post-meta { display:flex; align-items:center; gap:8px; font-size:11px; }',

      /* Status badges */
      '.blog-status { display:inline-flex; align-items:center; gap:4px; font-size:11px; }',
      '.blog-dot { width:8px; height:8px; border-radius:50%; display:inline-block; }',
      '.published-dot { background:var(--success,#22c55e); }',
      '.draft-dot { background:var(--text-muted,#888); }',

      /* Format badges */
      '.blog-format-badge { display:inline-block; padding:1px 6px; border-radius:4px; font-size:10px; font-weight:700; letter-spacing:0.3px; line-height:1.5; }',
      '.badge-md { background:#22c55e22; color:#22c55e; }',
      '.badge-html { background:#3b82f622; color:#3b82f6; }',
      '.badge-pdf { background:#ef444422; color:#ef4444; }',

      /* Editor */
      '.blog-editor { padding:20px; max-width:800px; }',
      '.blog-editor-empty { display:flex; align-items:center; justify-content:center; height:100%; color:var(--text-muted); font-size:14px; }',
      '.blog-editor-empty p { text-align:center; }',

      '.blog-editor-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:20px; }',
      '.blog-editor-header h3 { margin:0; font-size:18px; font-weight:600; }',
      '.blog-editor-actions { display:flex; gap:8px; }',

      '.blog-editor-form .form-group { margin-bottom:16px; }',

      /* File upload */
      '.blog-file-dropzone { border:2px dashed var(--border-color); border-radius:var(--radius-sm); padding:20px; text-align:center; cursor:pointer; transition:border-color 0.2s, background 0.2s; }',
      '.blog-file-dropzone:hover, .blog-dropzone-active { border-color:var(--accent); background:var(--accent-bg); }',
      '.blog-file-info { margin-top:8px; display:flex; align-items:center; font-size:13px; }',

      /* Content textarea */
      '.blog-content-textarea { min-height:300px; font-family:var(--font-mono,monospace); font-size:13px; line-height:1.5; resize:vertical; }',

      /* Inspection overlay */
      '.blog-inspection-overlay { position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.6); z-index:1000; display:flex; align-items:center; justify-content:center; }',
      '.blog-inspection-panel { background:var(--bg-card); border:1px solid var(--border-color); border-radius:var(--radius); width:700px; max-width:90vw; max-height:80vh; display:flex; flex-direction:column; }',
      '.blog-inspection-header { display:flex; align-items:center; justify-content:space-between; padding:16px 20px; border-bottom:1px solid var(--border-color); flex-shrink:0; }',
      '.blog-inspection-header h3 { margin:0; font-size:16px; font-weight:600; }',
      '.blog-inspection-body { flex:1; overflow-y:auto; padding:16px 20px; }',

      /* Commit list */
      '.blog-commit-list { display:flex; flex-direction:column; gap:4px; }',
      '.blog-commit-entry { display:flex; align-items:center; gap:12px; padding:8px 12px; border-radius:var(--radius-sm); cursor:pointer; transition:background 0.15s; }',
      '.blog-commit-entry:hover { background:var(--bg-hover); }',
      '.blog-commit-entry.commit-selected { background:var(--accent-bg); }',
      '.blog-commit-hash { font-family:var(--font-mono,monospace); font-size:12px; color:var(--accent); min-width:65px; }',
      '.blog-commit-date { font-size:11px; color:var(--text-muted); min-width:80px; }',
      '.blog-commit-msg { font-size:13px; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }',

      /* Commit content view */
      '.blog-commit-content-header { padding:8px 0; margin-bottom:8px; border-bottom:1px solid var(--border-color); }',
      '.blog-commit-content-pre { background:var(--bg-hover); border:1px solid var(--border-color); border-radius:var(--radius-sm); padding:16px; overflow:auto; max-height:400px; font-family:var(--font-mono,monospace); font-size:12px; line-height:1.6; white-space:pre-wrap; word-break:break-all; }',
    ].join('\n');
    document.head.appendChild(style);
  })();
})();
