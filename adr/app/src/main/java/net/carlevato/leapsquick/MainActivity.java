package net.carlevato.leapsquick;

import android.app.Activity; import android.os.Bundle; import android.widget.*;

public class MainActivity extends Activity {
  private static final int[] OPACITIES={255,210,160,105};
  public void onCreate(Bundle state) { super.onCreate(state); setContentView(R.layout.activity_main);
    EditText url=findViewById(R.id.url); Spinner transparency=findViewById(R.id.transparency); TextView status=findViewById(R.id.status);
    ArrayAdapter<String> options=new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"Solid grey","Light grey","Soft grey","Transparent grey"});
    transparency.setAdapter(options);
    url.setText(getSharedPreferences("leaps",0).getString("url","https://carlevato.net/leaps"));
    int savedOpacity=getSharedPreferences("leaps",0).getInt("widgetOpacity",210);
    for(int index=0;index<OPACITIES.length;index++) if(OPACITIES[index]==savedOpacity) transparency.setSelection(index);
    findViewById(R.id.save).setOnClickListener(v->{ String value=url.getText().toString().replaceAll("/+$",""); int opacity=OPACITIES[transparency.getSelectedItemPosition()]; getSharedPreferences("leaps",0).edit().putString("url",value).putInt("widgetOpacity",opacity).apply(); LeapsWidget.refreshAll(this,"Ready"); status.setText("Saved. Widget appearance updated."); });
  }
}
