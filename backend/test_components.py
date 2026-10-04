import sys
sys.path.insert(0, '.')
import database as db
db.init_db()
print('Database initialized successfully')

from ml.model import get_risk_model
model = get_risk_model()
print(f'ML Model loaded: {model.is_model_loaded()}')

from ml.fusion import get_fusion_engine
fusion = get_fusion_engine()
status = fusion.get_system_status()
print(f'Fusion engine mode: {status["fusion_mode"]}')

from tracking import get_worker_tracker
tracker = get_worker_tracker()
print(f'Tracker initialized: {len(tracker.get_all_tracks())} tracks')

from voice import get_voice_system
voice = get_voice_system()
print(f'Voice system: {voice.get_status()["active_provider"]}')

print('All components initialized successfully!')