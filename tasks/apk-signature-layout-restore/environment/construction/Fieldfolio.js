import React, {useState} from 'react';
import {AppRegistry, SafeAreaView, ScrollView, Text, TextInput, Pressable, StyleSheet} from 'react-native';

const initialDocuments = [
  {name: 'Harbour survey', project: 'Pier access', status: 'Synced'},
  {name: 'Concrete delivery receipt', project: 'West service road', status: 'Ready to upload'},
  {name: 'Equipment inspection', project: 'Cedar substation', status: 'Synced'},
];

function Fieldfolio() {
  const [documents, setDocuments] = useState(initialDocuments);
  const [query, setQuery] = useState('');
  const [message, setMessage] = useState('Your field notes, together.');
  const upload = () => {
    setMessage('Select a clear photo of the full document. Keep all four corners visible.');
    setDocuments(documents.map(document => ({...document, status: 'Synced'})));
  };
  return (
    <SafeAreaView style={styles.page}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.brand}>Fieldfolio</Text>
        <Text style={styles.caption}>{message}</Text>
        <TextInput style={styles.search} value={query} onChangeText={setQuery} placeholder="Find a document or project" />
        {documents.filter(document => `${document.name} ${document.project}`.toLowerCase().includes(query.toLowerCase())).map(document => (
          <Pressable key={document.name} style={styles.document} onPress={() => setMessage(document.project)}>
            <Text style={styles.title}>{document.name}</Text>
            <Text>{document.project}</Text>
            <Text style={styles.status}>{document.status}</Text>
          </Pressable>
        ))}
        <Pressable style={styles.button} onPress={upload}><Text style={styles.buttonLabel}>Upload document</Text></Pressable>
        <Text style={styles.caption}>Uploads remain on this device until the connection is available.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}
const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: '#f5f4ef'},
  content: {padding: 24, gap: 18},
  brand: {fontSize: 32, fontWeight: '700', color: '#134d43'},
  caption: {fontSize: 14, lineHeight: 21, color: '#52635e'},
  search: {backgroundColor: 'white', padding: 14, borderRadius: 8},
  document: {backgroundColor: 'white', padding: 18, borderRadius: 10, gap: 8},
  title: {fontSize: 18, fontWeight: '600'},
  status: {fontSize: 12, color: '#347468'},
  button: {backgroundColor: '#134d43', padding: 18, borderRadius: 8},
  buttonLabel: {color: 'white', textAlign: 'center', fontWeight: '600'},
});
AppRegistry.registerComponent('Fieldfolio', () => Fieldfolio);
