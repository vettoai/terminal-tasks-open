import {recognizeText} from '@infinitered/react-native-mlkit-text-recognition';
import * as FileSystem from 'expo-file-system';
import type {OcrLine} from '../forms/types';
import {prepareDiagnosticsImage} from './preprocess';

export async function readDiagnostics(uri: string): Promise<OcrLine[]> {
  const prepared = await prepareDiagnosticsImage(uri);
  try {
    const recognition = await recognizeText(prepared);
    return recognition.blocks.flatMap(block => block.lines.map(line => ({
      text: line.text,
      boundingBox: {
        left: line.frame.left,
        top: line.frame.top,
        width: line.frame.right - line.frame.left,
        height: line.frame.bottom - line.frame.top,
      },
    })));
  } finally {
    await FileSystem.deleteAsync(prepared, {idempotent: true});
  }
}
