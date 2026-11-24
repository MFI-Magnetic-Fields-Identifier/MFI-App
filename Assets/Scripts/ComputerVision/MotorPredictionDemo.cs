using System;
using UnityEngine;

namespace Mfi.ComputerVision
{
    public sealed class MotorPredictionDemo : MonoBehaviour
    {
        [SerializeField] private string apiBaseUrl = "http://127.0.0.1:8000";
        [SerializeField] private TextAsset testPhoto;
        [SerializeField] private string contentType = "image/png";
        [SerializeField, Min(1)] private int timeoutSeconds = 15;

        private void Start()
        {
            if (testPhoto != null)
            {
                SendTestPhoto();
            }
        }

        [ContextMenu("Enviar foto de teste")]
        public void SendTestPhoto()
        {
            if (!Application.isPlaying || !isActiveAndEnabled)
            {
                return;
            }
            if (testPhoto == null)
            {
                Debug.LogWarning("MFI: atribua a foto de teste no Inspector.", this);
                return;
            }

            MotorPredictionClient client;
            try
            {
                client = new MotorPredictionClient(apiBaseUrl, timeoutSeconds);
            }
            catch (ArgumentException error)
            {
                Debug.LogError($"MFI: {error.Message}", this);
                return;
            }

            Debug.Log("MFI: processando a foto de teste.", this);
            StartCoroutine(client.Predict(testPhoto.bytes, contentType, LogPrediction, LogError));
        }

        private void LogPrediction(MotorPrediction prediction)
        {
            Debug.Log($"MFI: estado da identificação: {prediction.status}", this);
            foreach (MotorCandidate candidate in prediction.candidates)
            {
                Debug.Log($"MFI: {candidate.model_id}, pontuação {candidate.score:F4}", this);
            }
        }

        private void LogError(string error)
        {
            Debug.LogError($"MFI: {error}", this);
        }
    }
}
