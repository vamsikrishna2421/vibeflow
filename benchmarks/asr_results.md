# VibeFlow speech-accuracy benchmark

Hard sentences (numbers, acronyms, names, homophones, jargon) rendered as fast text-to-speech in several accents, run through VibeFlow's own Transcriber. Machine: Intel(R) Core(TM) i7-8850H CPU @ 2.60GHz, 12 threads, Darwin.

## Accuracy + speed summary

| Model | Size | clips | avg WER | median WER | avg sec/clip | long passage |
|---|---|---|---|---|---|---|
| Phonon-2 (phonon-2) | ~160 MB | 18 | 15.0% | 13.3% | 0.35 | 5.6s for 85.8s, 15.3x realtime, WER 13.0% |
| Phonon-2.5 English (phonon-2.5-en) | ~160 MB | 18 | 15.8% | 15.4% | 0.30 | 6.5s for 85.8s, 13.2x realtime, WER 14.2% |
| Whisper small (small) | ~500 MB | 18 | 13.2% | 13.3% | 4.12 | 30.8s for 85.8s, 2.8x realtime, WER 12.3% |
| Whisper medium (medium) | ~1.5 GB | 18 | 10.8% | 13.3% | 8.28 | 69.0s for 85.8s, 1.2x realtime, WER 11.9% |

_WER = Word Error Rate (lower is better). 0% = perfect. Formatting counts: "18.7%" vs "18.7 percent" or "4,500" vs "4500" is an error for every engine._

## Transcriptions by case

### Case 1

**Reference:** The server at 192.168.0.14 returned HTTP error 503 after 4500 milliseconds.

- **phonon-2** (WER 36%, 0.51s): The server at 192168014 returned HDDP error 503 after 4500 milliseconds.
- **phonon-2.5-en** (WER 7%, 0.37s): The server at 192-168-0-14 returned HDDP error 503 after 4500 milliseconds.
- **small** (WER 14%, 3.87s): The server at 192.168.0.14 returned HTTP error 503 after 4,500 milliseconds.
- **medium** (WER 29%, 9.7s): The server at 192.168.0.1.4 returned HTTP error 503 after 4,500 milliseconds.

### Case 2

**Reference:** Deploy the Kubernetes pod using kubectl apply and verify the YAML configuration.

- **phonon-2** (WER 25%, 0.3s): Deploy the Cuba Needs pod using Cubectle Apply and verify the YAML configuration.
- **phonon-2.5-en** (WER 33%, 0.27s): Deploy the cube and needs pod using cube apply and verify the YAML configuration.
- **small** (WER 17%, 3.98s): Deploy the Kubernetes pod using CubectlApply and verify the YAML configuration.
- **medium** (WER 0%, 8.08s): Deploy the Kubernetes pod using kubectl apply and verify the YAML configuration.

### Case 3

**Reference:** Vamsi and Nguyen reviewed the Qwen and Gemma benchmark results on Tuesday.

- **phonon-2** (WER 33%, 0.24s): Vamzi and Muyen reviewed the Quin and Jemba benchmark results on Tuesday.
- **phonon-2.5-en** (WER 33%, 0.21s): Vamzi and Nuyen reviewed the Quinn and Jemma benchmark results on Tuesday.
- **small** (WER 33%, 5.32s): Vemsia Nuyen reviewed the Quinn and Gemma benchmark results on Tuesday.
- **medium** (WER 25%, 8.09s): Vamsee and Nuyen reviewed the Quinn and Gemma benchmark results on Tuesday.

### Case 4

**Reference:** They're driving to their house over there to debate the principal's core principle.

- **phonon-2** (WER 13%, 0.42s): They are driving to their house over there to debate the principle's core principle.
- **phonon-2.5-en** (WER 13%, 0.23s): They are driving to their house over there to debate the principle's core principle.
- **small** (WER 13%, 4.92s): They are driving to their house over there to debate the principle's core principle.
- **medium** (WER 13%, 8.17s): They are driving to their house over there to debate the principle's core principle.

### Case 5

**Reference:** The patient was prescribed 250 milligrams of amoxicillin to be taken twice daily.

- **phonon-2** (WER 0%, 0.32s): The patient was prescribed 250 milligrams of amoxicillin to be taken twice daily.
- **phonon-2.5-en** (WER 0%, 0.31s): The patient was prescribed 250 milligrams of amoxicillin to be taken twice daily.
- **small** (WER 0%, 5.06s): The patient was prescribed 250 milligrams of Amoxicillin to be taken twice daily.
- **medium** (WER 8%, 7.84s): The patient was prescribed 250 mg of Amoxicillin to be taken twice daily.

### Case 6

**Reference:** The meeting on March 3rd at 2:45 PM was rescheduled to the 17th at 11:30 AM.

- **phonon-2** (WER 0%, 0.41s): The meeting on march 3rd at 2:45 PM was rescheduled to the 17th at 11:30 AM.
- **phonon-2.5-en** (WER 28%, 0.31s): The meeting on March 3 at 2:45 p.m. was rescheduled to the 17th at 11:30 a.m.
- **small** (WER 22%, 3.11s): The meeting on March 3rd at 2.45pm was rescheduled to the 17th at 11.30am.
- **medium** (WER 0%, 8.64s): The meeting on March 3rd at 2.45 PM was rescheduled to the 17th at 11.30 AM.

### Case 7

**Reference:** Add 2.5 liters of water and heat it to 350 degrees Fahrenheit for 25 minutes.

- **phonon-2** (WER 0%, 0.32s): Add 2.5 liters of water and heat it to 350 degrees Fahrenheit for 25 minutes.
- **phonon-2.5-en** (WER 0%, 0.27s): Add 2.5 liters of water and heat it to 350 degrees Fahrenheit for 25 minutes.
- **small** (WER 0%, 3.01s): Add 2.5 liters of water and heat it to 350 degrees Fahrenheit for 25 minutes.
- **medium** (WER 0%, 7.99s): Add 2.5 liters of water and heat it to 350 degrees Fahrenheit for 25 minutes.

### Case 8

**Reference:** Third quarter revenue grew 18.7 percent to 4.2 million dollars year over year.

- **phonon-2** (WER 0%, 0.36s): Third quarter revenue grew 18.7 percent to 4.2 million dollars year over year.
- **phonon-2.5-en** (WER 13%, 0.27s): Third quarter revenue grew 18.7% to $4.2 million year over year.
- **small** (WER 20%, 4.07s): 3rd quarter revenue grew 18.7% to $4.2 million year over year.
- **medium** (WER 13%, 8.28s): Third quarter revenue grew 18.7% to $4.2 million year over year.

### Case 9

**Reference:** Run npm install, then npx vite build, and commit the changes to the main branch.

- **phonon-2** (WER 7%, 0.3s): Run NPM install, then NPX V build, and commit the changes to the main branch.
- **phonon-2.5-en** (WER 13%, 0.3s): Run NPM install, then npx vbuild, and commit the changes to the main branch.
- **small** (WER 13%, 5.19s): Run npm install, then npxv build, and commit the changes to the main branch.
- **medium** (WER 13%, 8.8s): Run npm install, then npxv build, and commit the changes to the main branch.

### Case 10

**Reference:** Please email john.doe@example.com and copy the team at support@acme.io.

- **phonon-2** (WER 21%, 0.4s): Please email John.com and copy the team at support at acme.io.
- **phonon-2.5-en** (WER 29%, 0.43s): Please email John.o at example.com and copy the team at support at akme.io.
- **small** (WER 14%, 4.74s): Please email john.do.example.com and copy the team at support.at.acme.io.
- **medium** (WER 14%, 8.6s): Please email john.doe at example.com and copy the team at support at acme.io.

### Case 11

**Reference:** We ordered croissants, gnocchi, and a jalapeno quesadilla for the office lunch.

- **phonon-2** (WER 25%, 0.27s): We ordered croissants, naughty, and a halapeno quesadillo for the office lunch.
- **phonon-2.5-en** (WER 25%, 0.3s): We ordered croissants, Noki, and a jalapenio cuesadilla for the office lunch.
- **small** (WER 0%, 4.46s): We ordered croissants, gnocchi, and a jalapeno quesadilla for the office lunch.
- **medium** (WER 0%, 8.16s): We ordered croissants, gnocchi, and a jalapeno quesadilla for the office lunch.

### Case 12

**Reference:** The NASDAQ fell 2.3 percent while the S&P 500 rose 0.8 percent on Friday.

- **phonon-2** (WER 6%, 0.33s): The Nasdaq fell 2.3 percent while the S and P 500 rose 0.8 percent on Friday.
- **phonon-2.5-en** (WER 24%, 0.33s): The Nasdaq fell 2.3% while the SP 500 rose 0.8% on Friday.
- **small** (WER 12%, 5.59s): The NASDAQ fell 2.3% while the S&P 500 rose 0.8% on Friday.
- **medium** (WER 12%, 8.44s): The NASDAQ fell 2.3% while the S&P 500 rose 0.8% on Friday.

### Case 13

**Reference:** Mitochondria produce ATP through the process of oxidative phosphorylation.

- **phonon-2** (WER 0%, 0.24s): Mitochondria produce ATP through the process of oxidative phosphorylation.
- **phonon-2.5-en** (WER 0%, 0.25s): Mitochondria produce ATP through the process of oxidative phosphorylation.
- **small** (WER 0%, 3.72s): Mitochondria produce ATP through the process of oxidative phosphorylation.
- **medium** (WER 0%, 7.56s): Mitochondria produce ATP through the process of oxidative phosphorylation.

### Case 14

**Reference:** Call me at 555 867 5309 or dial extension 42 any time after 5 PM.

- **phonon-2** (WER 20%, 0.37s): Call me at 5558675309 or dial extension 42 any time after 5 PM.
- **phonon-2.5-en** (WER 13%, 0.4s): Call me at 555 867 5309 or dial extension 42 any time after 5 p.m.
- **small** (WER 27%, 4.12s): Call me at 555-867-5309, or dial extension 42 anytime after 5pm.
- **medium** (WER 27%, 8.2s): Call me at 555-867-5309 or dial extension 42 anytime after 5 p.m.

### Case 15

**Reference:** The API uses OAuth 2.0 with JWT tokens sent over HTTPS on port 8443.

- **phonon-2** (WER 53%, 0.41s): The API uses our Orth 2.0 with JWT tokens sent over HTTPS on port eight four hundred and forty three.
- **phonon-2.5-en** (WER 20%, 0.37s): The API uses our Orth 2.0 with JWT token sent over HTTPS on port 8443.
- **small** (WER 7%, 4.15s): The API uses OAuth 2.0 with JWT token sent over HTTPS on port 8443.
- **medium** (WER 0%, 8.96s): The API uses OAuth 2.0 with JWT tokens sent over HTTPS on port 8443.

### Case 16

**Reference:** Notwithstanding the circumstances, the committee unanimously ratified the amended proposal.

- **phonon-2** (WER 0%, 0.37s): Notwithstanding the circumstances, the committee unanimously ratified the amended proposal.
- **phonon-2.5-en** (WER 0%, 0.27s): Notwithstanding the circumstances, the committee unanimously ratified the amended proposal.
- **small** (WER 10%, 2.83s): Notwithstanding the circumstances, the committee anonymously ratified the amended proposal.
- **medium** (WER 0%, 7.47s): Notwithstanding the circumstances, the committee unanimously ratified the amended proposal.

### Case 17

**Reference:** Schedule the cron job for 0 30 4 every Sunday and log to var slash log slash app.

- **phonon-2** (WER 22%, 0.36s): Schedule the crown job for 034 every Sunday and log to var slash log slash app.
- **phonon-2.5-en** (WER 17%, 0.31s): Schedule the Cron job for 034 every Sunday and log to var slash log slash app.
- **small** (WER 11%, 2.98s): Schedule the cron job for 0.34 every Sunday and log to var slash log slash app.
- **medium** (WER 17%, 7.93s): Schedule the cron job for 034 every Sunday and log to var slash log slash app.

### Case 18

**Reference:** Doctor Smith said the acetaminophen dosage should not exceed 3000 milligrams per day.

- **phonon-2** (WER 8%, 0.41s): Doctor Smith said the acetaminifond dosage should not exceed 3000 milligrams per day.
- **phonon-2.5-en** (WER 15%, 0.28s): Dr. Smith said the acetaminifan dosage should not exceed 3000 milligrams per day.
- **small** (WER 23%, 2.96s): Dr. Smith said the acetaminophen dosage should not exceed 3,000 milligrams per day.
- **medium** (WER 23%, 8.11s): Dr. Smith said the acetaminophen dosage should not exceed 3,000 milligrams per day.
