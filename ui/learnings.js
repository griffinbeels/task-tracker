// The Learnings overlay -- a read-only reader over ~/.claude/knowledge (see
// knowledge.py), so the cross-project record of how to build things well is
// one button away from whatever project's tracker is open, instead of a
// folder you have to remember exists. Escape closes it like every other
// overlay (see the list in ui/state.js).
//
// Every page it renders is Claude's own prose, not a hand-editable task file
// -- but everything below still builds elements and sets .textContent rather
// than reaching for innerHTML, the same discipline taskRow follows for user
// text (invariant 5). Nothing here depends on the source staying trusted.

// Every page opened this visit, oldest first, so Back can pop the current one
// off and reopen whatever is left on top. Reset each time the button opens
// the overlay fresh -- a page from the last visit is not where "Back" should
// ever lead.
let knowledgeHistory = [];

// A relative markdown link is written against the page that CONTAINS it, not
// against the knowledge root -- the same rule a browser applies to a page's
// own relative URLs. '..' pops a directory, '.' and empty segments are
// dropped, anything else is appended. knowledge.read_page only ever accepts
// a path already relative to the root, so this is the one place that math
// happens.
function resolveKnowledgeLink(fromPage, href) {
  const base = fromPage.split('/').slice(0, -1);
  for (const segment of href.split('/')) {
    if (segment === '.' || segment === '') continue;
    if (segment === '..') base.pop();
    else base.push(segment);
  }
  return base.join('/');
}

// Deliberately incomplete: headings, bullets, **bold**, `code`, and
// [text](link) is the whole subset a knowledge-base page is written in.
// Reads left to right once, so an earlier match's replacement text can never
// be re-scanned for a later construct.
const INLINE_MARKDOWN = /\*\*(.+?)\*\*|`([^`]+?)`|\[([^\]]+)\]\(([^)]+)\)/g;

function renderInline(container, text, page) {
  let cursor = 0;
  let match;
  INLINE_MARKDOWN.lastIndex = 0;
  while ((match = INLINE_MARKDOWN.exec(text))) {
    if (match.index > cursor) container.append(text.slice(cursor, match.index));
    const [, bold, code, label, href] = match;
    if (bold !== undefined) {
      const strong = document.createElement('strong');
      strong.textContent = bold;
      container.append(strong);
    } else if (code !== undefined) {
      const inlineCode = document.createElement('code');
      inlineCode.textContent = code;
      container.append(inlineCode);
    } else {
      const link = document.createElement('a');
      link.textContent = label;
      link.href = '#';
      if (/^https?:\/\//.test(href)) {
        link.onclick = event => { event.preventDefault(); callApi('open_external_url', href); };
      } else if (href.toLowerCase().endsWith('.md')) {
        link.onclick = event => {
          event.preventDefault();
          openKnowledgePage(resolveKnowledgeLink(page, href));
        };
      } else {
        // Neither a web link nor a page this overlay can open (e.g. a path
        // into the repo the knowledge base is documenting). Left in place and
        // readable rather than dropped, so the sentence around it still
        // reads; it simply does nothing when clicked.
        link.classList.add('md-link-inert');
        link.onclick = event => event.preventDefault();
      }
      container.append(link);
    }
    cursor = INLINE_MARKDOWN.lastIndex;
  }
  if (cursor < text.length) container.append(text.slice(cursor));
}

// Line-based on purpose: every construct in this subset (a heading, a
// bullet, a run of bold/code/link text) starts at the beginning of a line,
// and nothing in it spans one line into the next.
function renderMarkdown(body, markdown, page) {
  body.replaceChildren();
  let list = null;
  for (const line of markdown.split('\n')) {
    if (/^##\s+/.test(line)) {
      list = null;
      const heading = document.createElement('h4');
      heading.className = 'md-h2';
      renderInline(heading, line.replace(/^##\s+/, ''), page);
      body.append(heading);
    } else if (/^#\s+/.test(line)) {
      list = null;
      const heading = document.createElement('h3');
      heading.className = 'md-h1';
      renderInline(heading, line.replace(/^#\s+/, ''), page);
      body.append(heading);
    } else if (/^-\s+/.test(line)) {
      if (!list) {
        list = document.createElement('ul');
        list.className = 'md-bullets';
        body.append(list);
      }
      const item = document.createElement('li');
      renderInline(item, line.replace(/^-\s+/, ''), page);
      list.append(item);
    } else if (line.trim() === '') {
      list = null;
    } else {
      list = null;
      const paragraph = document.createElement('p');
      renderInline(paragraph, line, page);
      body.append(paragraph);
    }
  }
}

async function openKnowledgePage(relativePath) {
  const markdown = await callApi('read_knowledge_page', relativePath);
  if (markdown === API_FAILED) return;
  knowledgeHistory.push(relativePath);
  document.getElementById('learnings-back').hidden = knowledgeHistory.length < 2;
  renderMarkdown(document.getElementById('learnings-body'), markdown, relativePath);
}

document.getElementById('learnings-button').onclick = () => {
  knowledgeHistory = [];
  document.getElementById('learnings').hidden = false;
  openKnowledgePage('index.md');
};

// Pops the page on screen, then the one before it, and reopens THAT --
// openKnowledgePage pushes it straight back on, so history ends one entry
// shorter than it started, at the page Back is supposed to land on.
document.getElementById('learnings-back').onclick = () => {
  knowledgeHistory.pop();
  const previous = knowledgeHistory.pop();
  if (previous) openKnowledgePage(previous);
};

document.getElementById('learnings-close').onclick = () => {
  document.getElementById('learnings').hidden = true;
};
