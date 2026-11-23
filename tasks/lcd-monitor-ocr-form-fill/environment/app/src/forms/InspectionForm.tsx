import React, {useRef, useState} from 'react';
import {Button, Modal, ScrollView, Switch, Text, TextInput, View} from 'react-native';
import {CameraView, useCameraPermissions} from 'expo-camera';
import limits from '../../config/l3-3dx-limits.json';
import {readDiagnostics} from '../ocr/capture';
import {fillFormFromOcr} from '../ocr/ocrUtils';
import {bindingKey} from './types';
import type {FormControl, FormData} from './types';

export function InspectionForm({form, initialData}: {form: FormControl[]; initialData: FormData}) {
  const [data, setData] = useState(initialData);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [permission, requestPermission] = useCameraPermissions();
  const camera = useRef<CameraView>(null);

  async function photograph() {
    setBusy(true);
    setError('');
    try {
      const photo = await camera.current?.takePictureAsync({quality: 1});
      if (!photo) return;
      const lines = await readDiagnostics(photo.uri);
      const result = fillFormFromOcr(form, data, lines, limits);
      setData(result.formData);
      setWarnings(result.warnings);
      setCameraOpen(false);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }

  return <ScrollView contentContainerStyle={{padding: 20, gap: 12}}>
    {form.map((field, index) => {
      const key = bindingKey(field.Binding);
      if (field.Control === 'Label') return <Text key={index} style={{fontWeight: 'bold'}}>{field.Label}</Text>;
      if (field.Control === 'OCRCamera') return <Button key={index} title={field.Label} onPress={async () => {
        if (permission?.granted || (await requestPermission()).granted) setCameraOpen(true);
      }}/>;
      if (field.Control === 'Checkbox') return <View key={key}><Text>{field.Label}</Text><Switch value={Boolean(data[key])} onValueChange={value => setData({...data, [key]: value})}/></View>;
      return <View key={key}><Text>{field.Label}</Text><TextInput value={String(data[key] ?? '')} onChangeText={value => setData({...data, [key]: value})} style={{borderWidth: 1, borderColor: warnings.includes(key) ? '#a34012' : '#666', padding: 8}}/>{warnings.includes(key) && <Text style={{color: '#a34012'}}>Review this reading</Text>}</View>;
    })}
    <Modal visible={cameraOpen} onRequestClose={() => setCameraOpen(false)}>
      <CameraView ref={camera} style={{flex: 1}} facing="back"/>
      {!!error && <Text>{error}</Text>}
      <Button title={busy ? 'Reading screen…' : 'Read diagnostics'} disabled={busy} onPress={photograph}/>
      <Button title="Cancel" disabled={busy} onPress={() => setCameraOpen(false)}/>
    </Modal>
  </ScrollView>;
}
