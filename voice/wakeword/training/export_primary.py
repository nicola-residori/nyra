from pathlib import Path
import tensorflow as tf,numpy as np,hashlib,shutil
B=Path('/content/drive/MyDrive/nyra_openwakeword_it/oww-it-v1-001');P=B/'stream_v3/models/ehi_nira_it/best.keras';assert P.is_file(),P
out=Path('/content/nyra_italian_candidate_v1');out.mkdir(exist_ok=True)
m=tf.keras.models.load_model(P,compile=False);x=tf.keras.Input(batch_shape=(1,16,96),dtype=tf.float32);wrapper=tf.keras.Model(x,m(x,training=False));wrapper.export(str(out/'primary_saved_model'));c=tf.lite.TFLiteConverter.from_saved_model(str(out/'primary_saved_model'));c.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS];data=c.convert();p=out/'primary_ehi_nira.tflite';p.write_bytes(data);it=tf.lite.Interpreter(model_content=data);it.allocate_tensors();assert it.get_input_details()[0]['shape'].tolist()==[1,16,96]
for i in range(5):
 a=np.random.default_rng(i).normal(size=(1,16,96)).astype(np.float32);it.set_tensor(it.get_input_details()[0]['index'],a);it.invoke();assert np.allclose(it.get_tensor(it.get_output_details()[0]['index']),m(a,training=False).numpy(),atol=1e-4)
dest=B/'italian_candidate_v1';dest.mkdir(exist_ok=True);shutil.copy2(p,dest/p.name);assert hashlib.sha256(p.read_bytes()).digest()==hashlib.sha256((dest/p.name).read_bytes()).digest();print('PRIMARY_EXPORTED',p.stat().st_size,hashlib.sha256(p.read_bytes()).hexdigest(),flush=True)
