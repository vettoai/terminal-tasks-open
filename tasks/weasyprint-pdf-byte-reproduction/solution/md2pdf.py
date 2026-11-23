import html
import io
import json
import os
from pathlib import Path
import re
import sys

os.environ["SOURCE_DATE_EPOCH"] = "1790107499"

import markdown
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration


BODY_STYLESHEET = '''@page { size: A4; margin: 22mm 20mm 20mm 20mm; }
body { font-family: Georgia, "Times New Roman", serif; font-size: 10.5pt;
  line-height: 1.55; color: #1f2937; }
.cover { border-bottom: 2px solid #0f5132; padding-bottom: 10mm; margin-bottom: 8mm; }
.brand { font-family: Helvetica, Arial, sans-serif; font-size: 9pt; letter-spacing: .18em;
  text-transform: uppercase; color: #0f5132; margin: 0 0 4mm 0; }
.cover h1 { font-size: 21pt; line-height: 1.25; margin: 0; color: #111827; }
.meta { font-family: "Noto Serif", serif; font-size: 9.5pt; color: #6b7280;
  margin: 4mm 0 0 0; font-feature-settings: "onum" 1, "pnum" 1; }
h2 { font-family: "Noto Serif", serif; font-size: 13pt; color: #0f5132;
  margin: 9mm 0 3mm 0; page-break-after: avoid; font-feature-settings: "smcp" 1; }
p, li { orphans: 3; widows: 3; }
ol, ul { padding-left: 6mm; }
li { margin-bottom: 1.8mm; }
blockquote { border-left: 3px solid #d1d5db; margin: 4mm 0; padding: 0 0 0 4mm;
  color: #4b5563; font-style: italic; }
table { width: 100%; border-collapse: collapse; margin: 4mm 0 6mm 0;
  font-size: 9pt; page-break-inside: avoid; }
th { background: #f3f4f6; text-align: left; font-family: "Noto Serif", serif;
  font-size: 8.5pt; text-transform: none; letter-spacing: .04em; color: #374151;
  font-feature-settings: "smcp" 1, "c2sc" 1; }
th, td { border: 1px solid #d1d5db; padding: 2mm 2.5mm; vertical-align: top; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 9pt; background: #f3f4f6;
  padding: 0 1mm; }
hr { border: none; border-top: 1px solid #d1d5db; margin: 8mm 0 5mm 0; }
a { color: #0f5132; text-decoration: none; }
strong { color: #111827; }
'''

TEMPLATE = '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{title}</title></head><body><header class="cover"><p class="brand">ESTUÁRIO SERVIÇOS</p><h1>{title}</h1><p class="meta">Versão {version} · Jurídico e operações</p></header>{body_html}</body></html>'
FOLIO_TEMPLATE = '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"></head><body></body></html>'


def page_sections(document, pages):
    owners = {}
    current = ""
    for child in document.etree_element.find("body"):
        if child.tag == "header":
            continue
        if child.tag == "h2":
            current = "".join(child.itertext()).strip()
        for element in child.iter():
            owners[element] = current
    labels = []
    for page in pages:
        label = next((
            owners[box.element]
            for box in page._page_box.descendants()
            if getattr(box, "text", "").strip() and box.element in owners
        ), "")
        labels.append(label)
    return labels


PROOF_SET = (
    "billing-disputes.md",
    "cancellation-and-final-balance.md",
    "customer-notice-and-consent.md",
    "operational-responsibilities.md",
    "processing-and-retention.md",
    "reserve-reconciliation.md",
    "subscription-and-reserve-handoff.md",
)


def scoped_markdown(text):
    fragments = re.split(r"(?m)(?=^## )", text.strip())
    definition = re.compile(
        r"(?m)^ {0,3}\[(?!\^)([^\]\n]+)\]:[ \t]+(\S+)[ \t]*$"
    )
    defaults = {
        label.casefold(): target
        for label, target in definition.findall(fragments[0])
    }
    prepared = []
    alias_definitions = []
    for section_index, fragment in enumerate(fragments):
        bindings = dict(defaults)
        bindings.update(
            (label.casefold(), target)
            for label, target in definition.findall(fragment)
        )
        aliases = {}
        for binding_index, (label, target) in enumerate(bindings.items()):
            alias = f"estuario-scope-{section_index}-{binding_index}"
            aliases[label] = alias
            alias_definitions.append(f"[{alias}]: {target}")
        fragment = definition.sub("", fragment)

        def relabel(match):
            alias = aliases.get(match.group(2).casefold())
            return f"{match.group(1)}[{alias}]" if alias else match.group(0)

        prepared.append(re.sub(
            r"(\[[^\]\n]+\])\[([^\]\n]+)\]", relabel, fragment
        ))
    whole_document = "\n\n".join(prepared + alias_definitions)
    return markdown.markdown(
        whole_document,
        extensions=["tables", "sane_lists", "attr_list", "footnotes"],
        extension_configs={
            "footnotes": {
                "USE_DEFINITION_ORDER": False,
                "BACKLINK_TEXT": " voltar",
            }
        },
    )


def isolate_selected_destinations(layouts, selected_layout):
    for layout in layouts:
        if layout is selected_layout:
            continue
        for page in layout.pages:
            page.anchors = {}
            page.links = [link for link in page.links if link[0] != "internal"]


def source_document(source):
    text = source.read_text(encoding="utf-8")
    version_match = re.search(r"^\*\*Versão: ([^\n]+)\*\*\s*$", text, re.MULTILINE)
    title_match = re.search(r"^# ([^\n]+)$", text, re.MULTILINE)
    if version_match is None or title_match is None:
        raise ValueError("O documento precisa de versão e título.")
    version = version_match.group(1)
    title = title_match.group(1)
    for match in sorted((version_match, title_match), key=lambda item: item.start(), reverse=True):
        text = text[:match.start()] + text[match.end():]
    body_html = scoped_markdown(text)
    document = TEMPLATE.format(
        title=html.escape(title), version=html.escape(version), body_html=body_html
    )
    return title, document


def render(source_name, output_name):
    source = Path(source_name).resolve()
    root = Path.cwd().resolve()
    active_sources = [root / "docs" / "legal" / name for name in PROOF_SET]
    selected_title, selected_document = source_document(source)
    if source not in active_sources:
        matching_slots = [
            index for index, member in enumerate(active_sources)
            if source_document(member)[0] == selected_title
        ]
        if len(matching_slots) != 1:
            raise ValueError("A edição precisa de corresponder a uma peça do conjunto.")
        active_sources[matching_slots[0]] = source
    font_config = FontConfiguration()
    all_pages = []
    layouts = []
    selected_layout = None
    selected_sections = []
    selected_start = 0
    selected_stop = 0
    for member in active_sources:
        document = selected_document if member == source else source_document(member)[1]
        html_document = HTML(string=document, base_url=str(member.parent))
        layout = html_document.render(
            stylesheets=[CSS(string=BODY_STYLESHEET)], font_config=font_config
        )
        layouts.append(layout)
        if member == source:
            selected_layout = layout
            selected_sections = page_sections(html_document, layout.pages)
            selected_start = len(all_pages)
            selected_stop = selected_start + len(layout.pages)
        all_pages.extend(layout.pages)
    if selected_layout is None:
        raise ValueError("A peça pedida não pertence ao conjunto.")
    isolate_selected_destinations(layouts, selected_layout)
    proof_document = selected_layout.copy(all_pages)
    body_reader = PdfReader(io.BytesIO(proof_document.write_pdf()))
    writer = PdfWriter()
    writer.append(
        body_reader, pages=list(range(selected_start, selected_stop)), import_outline=True
    )
    writer.pdf_header = body_reader.pdf_header
    writer.add_metadata(dict(body_reader.metadata))
    writer._root_object[NameObject("/Lang")] = TextStringObject("pt-BR")
    folio_readers = []
    page_count = len(writer.pages)
    for page_number, page in enumerate(writer.pages, 1):
        section = json.dumps(selected_sections[page_number - 1], ensure_ascii=False)
        number = json.dumps(f"{page_number} / {page_count}")
        folio_stylesheet = (
            '@page { size: A4; margin: 22mm 20mm 20mm 20mm; '
            '@bottom-left { content: ' + section + '; width: 80%; text-align: left; '
            'font-family: Georgia, serif; font-size: 8pt; color: #6b7280; } '
            '@bottom-right { content: ' + number + '; width: 20%; text-align: right; '
            'font-family: Georgia, serif; font-size: 9pt; color: #6b7280; } }'
        )
        folio_bytes = HTML(string=FOLIO_TEMPLATE, base_url=str(source.parent)).write_pdf(
            stylesheets=[CSS(string=folio_stylesheet)]
        )
        folio_reader = PdfReader(io.BytesIO(folio_bytes))
        folio_readers.append(folio_reader)
        page.merge_page(folio_reader.pages[0], over=True, expand=False)
        page.compress_content_streams(level=6)
    writer.write(output_name)


if __name__ == "__main__":
    render(*sys.argv[1:])
