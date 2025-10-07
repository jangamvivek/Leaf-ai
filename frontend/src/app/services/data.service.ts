import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class DataService {
  private readonly baseUrl = environment.apiUrl.replace(/\/?$/, '/');

  constructor(private http: HttpClient) { }

  analyzeLeaf(image: File, prompt: string): Observable<any> {
    const form = new FormData();
    form.append('file', image, image.name);
    form.append('prompt', prompt || '');

    const headers = new HttpHeaders({});
    return this.http.post(`${this.baseUrl}analyze`, form, { headers }).pipe(
      catchError((error: HttpErrorResponse) => {
        return throwError(() => error);
      })
    );
  }
}
