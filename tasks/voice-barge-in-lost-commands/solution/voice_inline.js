function playAudioChunks() {
  if (currentAudio) return;
  while (audioChunks.length && cancelledStreams.has(audioChunks[0].stream)) audioChunks.shift();
  if (!audioChunks.length) return;
  const chunk = audioChunks.shift();
  const url = URL.createObjectURL(new Blob([chunk.bytes], { type: "audio/mpeg" }));
  const audio = new Audio(url);
  currentAudio = audio;
  currentUrl = url;
  audio.onplay = function () {
    if (currentAudio !== audio || cancelledStreams.has(chunk.stream)) {
      audio.pause();
      return;
    }
  };
  audio.onplaying = function () {
    if (currentAudio !== audio || cancelledStreams.has(chunk.stream)) {
      audio.pause();
      return;
    }
    ttsPlaying = true;
    showStopBtns(true);
  };
  function finish() {
    URL.revokeObjectURL(url);
    if (currentAudio !== audio) return;
    currentAudio = null;
    currentUrl = null;
    ttsPlaying = false;
    showStopBtns(false);
    playAudioChunks();
  }
  audio.onended = finish;
  audio.onerror = finish;
  audio.play().catch(finish);
}
