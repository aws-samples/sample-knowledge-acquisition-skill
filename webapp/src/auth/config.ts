export const authConfig = {
  userPoolId: import.meta.env.VITE_USER_POOL_ID || '',
  clientId: import.meta.env.VITE_CLIENT_ID || '',
  region: import.meta.env.VITE_REGION || 'eu-west-1',
};
