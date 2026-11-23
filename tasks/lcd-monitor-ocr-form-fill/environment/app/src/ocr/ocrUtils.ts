import {bindingKey} from '../forms/types';
import type {FormControl, FormData, Limits, OcrFillResult, OcrLine} from '../forms/types';

function labelText(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9.]/g, '');
}

function centre(line: OcrLine): number {
  return line.boundingBox.top + line.boundingBox.height / 2;
}

export function fillFormFromOcr(
  form: FormControl[],
  formData: FormData,
  ocrResult: OcrLine[],
  limits: Limits,
): OcrFillResult {
  const result = {...formData};
  const warnings: string[] = [];
  const values = ocrResult.filter(line => /^[+\-–—−]?[\dB.]+(?:\s+(?:psi|A|mA|V|kV|degC))?$/.test(line.text.trim()));
  const labels = ocrResult.filter(line => !values.includes(line));

  // Associate the recognised rows with the template's text controls.
  for (const line of labels) {
    const nearest = [...values].sort((first, second) =>
      Math.abs(centre(first) - centre(line)) - Math.abs(centre(second) - centre(line)),
    )[0];
    if (!nearest) continue;
    const text = labelText(line.text);
    for (const field of form) {
      if (field.Control !== 'SmartText') continue;
      if (!labelText(field.Label).includes(text)) continue;
      const key = bindingKey(field.Binding);
      result[key] = nearest.text.trim();
      const limit = limits[field.Label];
      if (limit && 'min' in limit) {
        const numeric = Number.parseFloat(nearest.text);
        if (numeric < limit.min || numeric > limit.max) warnings.push(key);
      }
    }
  }
  return {formData: result, warnings};
}
