import React from 'react';
import {SafeAreaView} from 'react-native';
import {InspectionForm} from './src/forms/InspectionForm';
import form from './src/forms/diagnostics.json';
import type {FormControl} from './src/forms/types';

export default function App() {
  return <SafeAreaView style={{flex: 1}}><InspectionForm form={form as FormControl[]} initialData={{interlocks_checked: false}}/></SafeAreaView>;
}
