# VoiceVis

**A mathematical attempt to understand vocal gender**

# Abstract

bla bbla bla

# Introduction

## Background
Verktyg för att analysera
- voice tools (app)
- spectrus/spectrogram
- Genderfluent (app)
- https://voice.accalia.gay/
- "normal audio recording"


## Literature review
## Problem statement
## Objectives and hypothesis



- Hypothesis 1: Vocal size ...
- Hypothesis 2: Vocal weight can be understood as a spectral slope where light voices have less energy in high frequencies.
- Hypothesis 3: Fullness can be described as a combination of size and weight.



# Methods

A custom application was written as to enable analysis and visualsisation of relevant vocal features.

The following high level method was used:
1. Acquire samples with vocal features, hopefully in isolation. Mainly from the Selene Archive [[1]](#selenearchive).
2. Extract audio features using Opensmile [[2]](#opensmile) [[3]](#genevaminimalistic) and custom signal processing.
5. The features was visualised in scatter plots. Subjective judgement was used to set appropriate min/max y scale limits. Annotations were added to keep track of the changes in the voice samples.
4. Target areas was visually set for the target voice gender. For each feature, multiple recordings from the Speech Accent Archive [[4]](#speechaccent) was used to evaluate these target areas.

## Opensmile features
vilka används

## Custom signal processing
- bandbredder
- weight

# Results
# Discussion
# Conclusion
# References


<a id="selenearchive">[1]</a> CosMarm et al (2024). "An organized collection of Selene Da Silva’s clips" <https://github.com/selenearchive/selenearchive.github.io>

<a id="opensmile">[2]</a> Florian Eyben, Martin Wöllmer, Björn Schuller (2016).  "openSMILE - The Munich Versatile and Fast Open-Source Audio Feature Extractor", Proc. ACM Multimedia (MM), ACM, Florence, Italy, ISBN 978-1-60558-933-6, pp. 1459-1462, 25.-29.10.2010.

<a id="genevaminimalistic">[3]</a> F. Eyben et al. (2015). "The Geneva Minimalistic Acoustic Parameter Set (GeMAPS) for Voice Research and Affective Computing," in IEEE Transactions on Affective Computing, vol. 7, no. 2, pp. 190-202, 1 April-June 2016, doi: 10.1109/TAFFC.2015.2457417. keywords: {Speech;Mel frequency cepstral coefficient;Standards;Harmonic analysis;Licenses;Frequency measurement;Affective Computing;Acoustic Features;Standard;Emotion Recognition;Speech Analysis;Geneva Minimalistic Parameter Set;Affective computing;acoustic features;standard;emotion recognition;speech analysis;geneva minimalistic parameter set}, 

<a id="speechaccent">[4]</a> Weinberger, Steven. (2015). "Speech Accent Archive" George Mason University, <http://accent.gmu.edu>


## List of audio samples used

### Size

<a id="hellosize">[A]</a> Da Silva, Selene (2022). "hello size" https://clyp.it/zegsbgqv

<a id="largetosmall">[B]</a> Da Silva, Selene (2022). "large to small" https://clyp.it/eraggfqe

<a id="sizev2">[C]</a> Da Silva, Selene (2022). "Size v2" https://clyp.it/jdquw5ac

### Weight
<a id="heavytolight">[D]</a> Da Silva, Selene (2022). "heavy to light" https://clyp.it/ydistdix

<a id="increasingweight">[E]</a> Da Silva, Selene (2022). "increasing weight with a static pitch" https://clyp.it/1xsaw5bc

<a id="pitchslide">[E]</a> Da Silva, Selene (2023). "pitch slide weight exploration" https://clyp.it/1ytjkdh4

<a id="weightmonika">[G]</a> Da Silva, Selene (2022). "weight monika" https://clyp.it/jxbetfwf


