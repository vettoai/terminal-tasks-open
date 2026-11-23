import * as Y from 'yjs'

export function clauses(document: Y.Doc) {
  return document.getXmlFragment('default').toArray() as Y.XmlElement[]
}

export function clauseText(clause: Y.XmlElement): Y.XmlText {
  return (clause.get(0) as Y.XmlElement).get(0) as Y.XmlText
}

export function jsonClauses(json: any): { id: string; text: string }[] {
  return json.content.map((clause: any) => ({
    id: clause.attrs.clauseId,
    text: (clause.content[0].content || []).map((part: any) => part.text || '').join(''),
  }))
}
