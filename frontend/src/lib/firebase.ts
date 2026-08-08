import { initializeApp, getApps, getApp } from "firebase/app";
import { getAuth, GoogleAuthProvider } from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyAbuWWS89JrdUd6JXkjG9N96TTB3H8ov5E",
  authDomain: "project-edadbb90-c880-4851-84d.firebaseapp.com",
  projectId: "project-edadbb90-c880-4851-84d",
  storageBucket: "project-edadbb90-c880-4851-84d.firebasestorage.app",
  messagingSenderId: "172052964630",
  appId: "1:172052964630:web:053aa692b9f8b28331dc37",
  measurementId: "G-PHG3TNS8P9",
};

const app = !getApps().length ? initializeApp(firebaseConfig) : getApp();
const auth = getAuth(app);
const googleProvider = new GoogleAuthProvider();

export { app, auth, googleProvider };
