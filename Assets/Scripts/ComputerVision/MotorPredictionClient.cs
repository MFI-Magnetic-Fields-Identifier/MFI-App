using System;
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

namespace Mfi.ComputerVision
{
    [Serializable]
    public sealed class MotorCandidate
    {
        public string model_id;
        public float score;
    }

    [Serializable]
    public sealed class MotorPrediction
    {
        public MotorCandidate[] candidates;
        public string status;
    }

    public sealed class MotorPredictionClient
    {
        public const int MaxPhotoBytes = 8 * 1024 * 1024;

        private readonly string predictionUrl;
        private readonly int timeoutSeconds;

        public MotorPredictionClient(string apiBaseUrl, int timeoutSeconds = 15)
        {
            if (!Uri.TryCreate(apiBaseUrl, UriKind.Absolute, out Uri uri)
                || (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps)
                || string.IsNullOrEmpty(uri.Host) || uri.Query.Length != 0 || uri.Fragment.Length != 0)
            {
                throw new ArgumentException("Informe uma URL HTTP ou HTTPS válida para a API.", nameof(apiBaseUrl));
            }
            if (timeoutSeconds < 1)
            {
                throw new ArgumentOutOfRangeException(nameof(timeoutSeconds));
            }
            predictionUrl = uri.GetLeftPart(UriPartial.Path).TrimEnd('/') + "/predict";
            this.timeoutSeconds = timeoutSeconds;
        }

        public IEnumerator Predict(
            byte[] image, string contentType, Action<MotorPrediction> onSuccess, Action<string> onError)
        {
            if (image == null || image.Length == 0 || image.Length > MaxPhotoBytes)
            {
                onError("Selecione uma foto de até 8 MiB.");
                yield break;
            }
            if (contentType != "image/jpeg" && contentType != "image/png" && contentType != "image/webp")
            {
                onError("Use JPEG, PNG ou WebP.");
                yield break;
            }

            using var request = new UnityWebRequest(predictionUrl, UnityWebRequest.kHttpVerbPOST)
            {
                uploadHandler = new UploadHandlerRaw(image) { contentType = contentType },
                downloadHandler = new DownloadHandlerBuffer(),
                timeout = timeoutSeconds,
                redirectLimit = 0
            };
            request.SetRequestHeader("Accept", "application/json");

            UnityWebRequestAsyncOperation operation;
            try
            {
                operation = request.SendWebRequest();
            }
            catch (InvalidOperationException error)
            {
                onError($"Não foi possível iniciar o envio: {error.Message}");
                yield break;
            }
            yield return operation;

            if (request.result == UnityWebRequest.Result.ProtocolError)
            {
                string detail = ParseJson<ApiError>(request.downloadHandler.text)?.detail;
                onError($"HTTP {request.responseCode}: {detail ?? request.error}");
                yield break;
            }
            if (request.result != UnityWebRequest.Result.Success)
            {
                onError($"Falha de comunicação com a API: {request.error}");
                yield break;
            }

            MotorPrediction prediction = ParseJson<MotorPrediction>(request.downloadHandler.text);
            if (!IsValid(prediction))
            {
                onError("A API retornou uma previsão inválida.");
                yield break;
            }

            onSuccess(prediction);
        }

        private static T ParseJson<T>(string json) where T : class
        {
            try
            {
                return JsonUtility.FromJson<T>(json);
            }
            catch (ArgumentException)
            {
                return null;
            }
        }

        private static bool IsValid(MotorPrediction prediction)
        {
            if (prediction?.candidates == null || prediction.candidates.Length == 0)
            {
                return false;
            }
            if (prediction.status != "accepted" && prediction.status != "needs_confirmation"
                && prediction.status != "unknown")
            {
                return false;
            }
            foreach (MotorCandidate candidate in prediction.candidates)
            {
                if (candidate == null || string.IsNullOrWhiteSpace(candidate.model_id)
                    || float.IsNaN(candidate.score) || candidate.score < 0 || candidate.score > 1)
                {
                    return false;
                }
            }
            return true;
        }

        [Serializable]
        private sealed class ApiError
        {
            public string detail;
        }
    }
}
