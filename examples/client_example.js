// Factor AI API 클라이언트 예제 (JavaScript/Node.js)
const fetch = require('node-fetch'); // npm install node-fetch@2
const fs = require('fs');
const FormData = require('form-data'); // npm install form-data

const BASE_URL = 'http://localhost:7000';

class FactorAIClient {
  constructor(baseUrl = BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  async healthCheck() {
    const response = await fetch(`${this.baseUrl}/health`);
    return await response.json();
  }

  async imageToThreeD(imagePath, extraMeta = {}) {
    const formData = new FormData();
    formData.append('task', 'image_to_3d');
    formData.append('image_file', fs.createReadStream(imagePath));
    formData.append('json', JSON.stringify(extraMeta));

    const response = await fetch(`${this.baseUrl}/v1/process/modelling`, {
      method: 'POST',
      body: formData,
      headers: formData.getHeaders()
    });

    const result = await response.json();
    if (result.status === 'error') {
      throw new Error(`API Error: ${result.error}`);
    }
    return result.data;
  }

  async textToThreeD(prompt, quality = 'medium') {
    const payload = {
      task: 'text_to_3d',
      prompt,
      model: 'flux-kontext',
      quality,
      output: { format: 'glb', unit: 'mm', scale: 1.0 },
      printer: { device_uuid: 'test-device', auto_slice: false, print: false },
      metadata: { session_id: 'test', source: 'api', user_id: 'test' }
    };

    const response = await fetch(`${this.baseUrl}/v1/process/modelling`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await response.json();
    if (result.status === 'error') {
      throw new Error(`API Error: ${result.error}`);
    }
    return result.data;
  }

  async getModellingStatus(taskId) {
    const response = await fetch(`${this.baseUrl}/v1/process/modelling/${taskId}`);
    const result = await response.json();
    if (result.status === 'error') {
      throw new Error(`API Error: ${result.error}`);
    }
    return result.data;
  }

  async waitForCompletion(taskId, pollInterval = 5000, timeout = 1200000) {
    const startTime = Date.now();

    while (true) {
      if (Date.now() - startTime > timeout) {
        throw new Error(`Task ${taskId} timeout after ${timeout}ms`);
      }

      const statusData = await this.getModellingStatus(taskId);
      const status = (statusData.status || '').toUpperCase();
      const progress = statusData.progress || 0;

      console.log(`Status: ${status}, Progress: ${progress}%`);

      if (status === 'SUCCEEDED') {
        return statusData;
      } else if (status === 'FAILED') {
        throw new Error(`Task ${taskId} failed`);
      }

      await new Promise(resolve => setTimeout(resolve, pollInterval));
    }
  }

  async cleanModel(taskId = null, glbPath = null) {
    if (!taskId && !glbPath) {
      throw new Error('Either taskId or glbPath must be provided');
    }

    const payload = {};
    if (taskId) payload.task_id = taskId;
    if (glbPath) payload.glb_path = glbPath;

    const response = await fetch(`${this.baseUrl}/v1/process/clean-model`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await response.json();
    if (result.status === 'error') {
      throw new Error(`API Error: ${result.error}`);
    }
    return result.data;
  }

  async downloadFile(url, savePath) {
    if (url.startsWith('/')) {
      url = `${this.baseUrl}${url}`;
    }

    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Download failed: ${response.statusText}`);
    }

    const buffer = await response.buffer();
    fs.writeFileSync(savePath, buffer);
    console.log(`Downloaded: ${savePath}`);
  }
}

// ===== 사용 예제 =====

async function main() {
  const client = new FactorAIClient();

  try {
    // 예제 1: 헬스 체크
    console.log('=== 헬스 체크 ===');
    const health = await client.healthCheck();
    console.log(health);
    console.log();

    // 예제 2: 이미지 → 3D 모델 (자동 완료)
    console.log('=== 이미지 → 3D 모델 ===');
    const result = await client.imageToThreeD('test_image.png');
    console.log('Task ID:', result.task_id);
    console.log('Download URL:', result.download_url);

    // 파일 다운로드
    await client.downloadFile(result.download_url, 'output_model.glb');
    console.log();

    // 예제 3: 텍스트 → 3D 모델 (폴링 필요)
    console.log('=== 텍스트 → 3D 모델 ===');
    const textResult = await client.textToThreeD('a cute robot');
    const taskId = textResult.task_id;
    console.log('Task ID:', taskId);

    // 완료까지 대기
    const completed = await client.waitForCompletion(taskId);
    console.log('완료! Download URL:', completed.download_url);

    // 파일 다운로드
    await client.downloadFile(completed.download_url, 'robot_model.glb');
    console.log();

    // 예제 4: Blender 후처리
    console.log('=== Blender 후처리 ===');
    const cleanResult = await client.cleanModel('0199e0be-35eb-754a-a02c-642c480e63de');
    console.log('Cleaned GLB:', cleanResult.cleaned_glb_url);
    console.log('STL:', cleanResult.stl_url);

    // 파일 다운로드
    await client.downloadFile(cleanResult.cleaned_glb_url, 'cleaned_model.glb');
    await client.downloadFile(cleanResult.stl_url, 'model.stl');

  } catch (error) {
    console.error('Error:', error.message);
  }
}

// Node.js에서 실행 시
if (require.main === module) {
  main();
}

module.exports = FactorAIClient;
