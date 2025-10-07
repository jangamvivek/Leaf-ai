import { Component } from '@angular/core';
import { DataService } from '../../services/data.service';

@Component({
  selector: 'app-upload',
  standalone: false,
  templateUrl: './upload.component.html',
  styleUrl: './upload.component.css'
})
export class UploadComponent {
  readonly maxBytes = 10 * 1024 * 1024; // 10 MB
  readonly allowedTypes = ['image/png', 'image/jpeg'];

  isDragOver = false;
  selectedFile: File | null = null;
  errorMessage = '';
  prompt = '';

  private resetError(): void {
    this.errorMessage = '';
  }

  private setError(message: string): void {
    this.errorMessage = message;
  }

  private validateFile(file: File): boolean {
    if (!this.allowedTypes.includes(file.type)) {
      this.setError('Only PNG and JPG/JPEG files are allowed.');
      return false;
    }
    if (file.size > this.maxBytes) {
      this.setError('File is too large. Maximum size is 10 MB.');
      return false;
    }
    this.resetError();
    return true;
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) {
      return;
    }
    const file = input.files[0];
    if (this.validateFile(file)) {
      this.selectedFile = file;
    } else {
      this.selectedFile = null;
    }
    input.value = '';
  }

  handleDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver = true;
  }

  handleDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver = false;
  }

  handleDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver = false;
    const files = event.dataTransfer?.files;
    if (!files || files.length === 0) {
      return;
    }
    const file = files[0];
    if (this.validateFile(file)) {
      this.selectedFile = file;
    } else {
      this.selectedFile = null;
    }
  }

  clearFile(): void {
    this.selectedFile = null;
    this.resetError();
  }

  isLoading = false;
  result: any = null;
  resultText = '';
  resultModel = '';

  constructor(private dataService: DataService) {}

  submit(): void {
    if (!this.selectedFile || this.errorMessage) {
      return;
    }
    this.isLoading = true;
    this.result = null;
    this.resultText = '';
    this.resultModel = '';
    this.dataService.analyzeLeaf(this.selectedFile, this.prompt).subscribe({
      next: (res) => {
        this.result = res;
        this.extractResult(res);
        this.isLoading = false;
      },
      error: (err) => {
        this.setError(err?.error?.detail || 'Failed to analyze image. Please try again.');
        this.isLoading = false;
      }
    });
  }

  private extractResult(res: any): void {
    try {
      // Handle custom backend shape
      if (res?.success && res?.data) {
        const data = res.data;
        this.resultText = data?.message || '';
        this.resultModel = '';
        return;
      }

      // Perplexity OpenAI-compatible response shape
      const choice = res?.choices?.[0];
      const message = choice?.message;
      const content = message?.content;
      if (Array.isArray(content)) {
        // some responses may be array of content parts
        const textPart = content.find((p: any) => p?.type === 'output_text' || p?.type === 'text');
        this.resultText = textPart?.text || '';
      } else if (typeof content === 'string') {
        this.resultText = content;
      } else if (message?.content?.text) {
        this.resultText = message.content.text;
      }
      this.resultModel = res?.model || '';
    } catch {
      this.resultText = '';
    }
  }
}
