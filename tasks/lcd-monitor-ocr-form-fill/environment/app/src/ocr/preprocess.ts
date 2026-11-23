import * as FileSystem from 'expo-file-system';
import {OpenCV, ObjectType, DataTypes, ColorConversionCodes} from 'react-native-fast-opencv';

export async function prepareDiagnosticsImage(uri: string): Promise<string> {
  const encoded = await FileSystem.readAsStringAsync(uri, {encoding: FileSystem.EncodingType.Base64});
  try {
    const source = OpenCV.base64ToMat(encoded);
    const grey = OpenCV.createObject(ObjectType.Mat, 0, 0, DataTypes.CV_8U);
    OpenCV.invoke('cvtColor', source, grey, ColorConversionCodes.COLOR_BGR2GRAY);
    const output = OpenCV.toJSValue(grey, 'jpeg');
    const target = `${FileSystem.cacheDirectory}diagnostics-${Date.now()}.jpg`;
    await FileSystem.writeAsStringAsync(target, output.base64, {encoding: FileSystem.EncodingType.Base64});
    return target;
  } finally {
    OpenCV.clearBuffers();
  }
}
