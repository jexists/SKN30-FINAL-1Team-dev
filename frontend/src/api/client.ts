import axios from 'axios'

import { env } from '@/config/env'

export const client = axios.create({
  baseURL: `${env.apiBaseUrl}/api`,
  timeout: 10_000,
  withCredentials: true,
})
