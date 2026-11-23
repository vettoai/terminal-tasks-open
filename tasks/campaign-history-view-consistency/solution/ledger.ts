export function decodeCollections(text: string): unknown {
  const preserved = text.replace(/"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g, token => {
    if (token.startsWith('"') || !/^-?\d+$/.test(token) || Number.isSafeInteger(Number(token))) return token;
    return JSON.stringify(token);
  });
  return JSON.parse(preserved);
}
